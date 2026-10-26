"""Load test of POST /api/invoices/extract with a fake, slow model. No API cost.

    uv run python -m scripts.load_extraction --requests 200 --delay 1.0

Every request waits --delay seconds inside the "model", like a real call would.
Run in one event loop and against the TEST database (never the development one).
It shows how many requests the app can have waiting for the model at the same
time, which is what async buys: the wait does not hold a thread.
"""

import argparse
import asyncio
import itertools
import statistics
import time
from collections import Counter
from decimal import Decimal

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from invoice_api.config import settings
from invoice_api.database import get_db
from invoice_api.main import app
from invoice_api.models import Base, Invoice, LlmCall, Supplier, User
from invoice_api.schemas.extraction import ExtractedInvoice
from invoice_api.security import create_access_token, hash_password
from invoice_api.services.concurrency import InFlightLimit, get_in_flight_limit
from invoice_api.services.extraction import (
    Attempt,
    AttemptOutcome,
    ExtractionResult,
    get_extractor,
)

TEST_DB_NAME = "invoice_test"
EMAIL = "load-test@example.com"


class SlowExtractor:
    model = "fake-model"

    def __init__(self, delay: float):
        self._delay = delay
        self._numbers = itertools.count(1)

    async def extract(self, text, categories=()):
        await asyncio.sleep(self._delay)
        invoice = ExtractedInvoice.model_validate(
            {
                "supplier_name": "Load Test S.L.",
                "invoice_number": f"LT-{next(self._numbers)}",
                "issue_date": "2026-03-15",
                "base_amount": "100.00",
                "tax_amount": "21.00",
                "total_amount": "121.00",
                "currency": "EUR",
            }
        )
        attempt = Attempt(AttemptOutcome.OK, input_tokens=10, output_tokens=10, latency_ms=0)
        return ExtractionResult(invoice, [attempt])


async def main(requests: int, delay: float, limit: int) -> None:
    url = make_url(settings.DATABASE_URL).set(database=TEST_DB_NAME)
    assert url.database == TEST_DB_NAME  # never touch another database
    engine = create_async_engine(url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with sessions() as db:
        user = User(email=EMAIL, hashed_password=hash_password("load-test-password"))
        db.add(user)
        await db.commit()
        user_id = user.id
    headers = {"Authorization": f"Bearer {create_access_token(user_id)}"}

    async def session_per_request():
        async with sessions() as db:
            yield db

    in_flight = InFlightLimit(limit)
    extractor = SlowExtractor(delay)  # one instance: it numbers the invoices
    app.dependency_overrides[get_db] = session_per_request
    app.dependency_overrides[get_extractor] = lambda: extractor
    app.dependency_overrides[get_in_flight_limit] = lambda: in_flight
    settings.USER_DAILY_BUDGET_USD = Decimal(1000)
    settings.GLOBAL_DAILY_BUDGET_USD = Decimal(1000)

    latencies: list[float] = []
    statuses: Counter[int] = Counter()

    async def one(client: AsyncClient) -> None:
        started = time.perf_counter()
        response = await client.post(
            "/api/invoices/extract", json={"text": "synthetic invoice"}, headers=headers
        )
        latencies.append(time.perf_counter() - started)
        statuses[response.status_code] += 1

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://load"
        ) as client:
            started = time.perf_counter()
            await asyncio.gather(*(one(client) for _ in range(requests)))
            total = time.perf_counter() - started
    finally:
        app.dependency_overrides.clear()
        async with sessions() as db:
            for model in (Invoice, Supplier, LlmCall):
                await db.execute(delete(model).where(model.user_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()
        await engine.dispose()

    latencies.sort()
    print(f"{requests} requests, model delay {delay}s, at most {limit} in flight")
    print(f"  total time      {total:6.2f}s  (one after the other: {requests * delay:.0f}s)")
    print(f"  latency median  {statistics.median(latencies):6.2f}s")
    print(f"  latency p95     {latencies[int(len(latencies) * 0.95) - 1]:6.2f}s")
    print(f"  statuses        {dict(statuses)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--limit", type=int, default=1000, help="cap on calls in flight")
    args = parser.parse_args()
    # psycopg cannot run in async mode on Windows' default ProactorEventLoop.
    asyncio.run(
        main(args.requests, args.delay, args.limit), loop_factory=asyncio.SelectorEventLoop
    )
