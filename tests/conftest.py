import asyncio
from collections.abc import AsyncGenerator, Callable, Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from invoice_api.config import settings
from invoice_api.database import get_db
from invoice_api.main import app
from invoice_api.models import Base, LlmCall

TEST_DB_NAME = "invoice_test"
# What Starlette's TestClient used to report as the client IP.
DEFAULT_CLIENT = ("testclient", 50000)


def pytest_asyncio_loop_factories(config: pytest.Config, item: pytest.Item) -> Mapping:
    # psycopg cannot run in async mode on Windows' default ProactorEventLoop.
    return {"selector": asyncio.SelectorEventLoop}


@pytest.fixture(scope="session")
async def engine() -> AsyncGenerator[AsyncEngine]:
    url = make_url(settings.DATABASE_URL).set(database=TEST_DB_NAME)
    # Safety guard: never run destructive setup against a non-test database.
    assert url.database == TEST_DB_NAME

    test_engine = create_async_engine(url)
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
async def db(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    async with engine.connect() as connection:
        outer_transaction = await connection.begin()
        # commit()/rollback() inside the app only affect a SAVEPOINT of the
        # outer transaction, which is rolled back when the test ends.
        session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await outer_transaction.rollback()


def make_client(client_address: tuple[str, int] = DEFAULT_CLIENT) -> AsyncClient:
    """A client of the app that the server sees as coming from `client_address`."""
    return AsyncClient(
        transport=ASGITransport(app=app, client=client_address), base_url="http://test"
    )


@pytest.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient]:
    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with make_client() as test_client:
        yield test_client
    app.dependency_overrides.clear()


PASSWORD = "test-password-123"


async def create_user(client: AsyncClient, email: str, password: str = PASSWORD) -> dict:
    response = await client.post(
        "/api/auth/register", json={"email": email, "password": password}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def login_headers(
    client: AsyncClient, email: str, password: str = PASSWORD
) -> dict[str, str]:
    # The login endpoint takes form data (OAuth2 spec), hence data= and not json=.
    response = await client.post(
        "/api/auth/login", data={"username": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
async def headers_a(client: AsyncClient) -> dict[str, str]:
    await create_user(client, "a@example.com")
    return await login_headers(client, "a@example.com")


@pytest.fixture
async def headers_b(client: AsyncClient) -> dict[str, str]:
    await create_user(client, "b@example.com")
    return await login_headers(client, "b@example.com")


@pytest.fixture
def make_category(client: AsyncClient) -> Callable[..., dict]:
    async def _make(headers: dict[str, str], name: str = "Utilities") -> dict:
        response = await client.post("/api/categories", json={"name": name}, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture
def make_supplier(client: AsyncClient) -> Callable[..., dict]:
    async def _make(headers: dict[str, str], name: str = "Acme S.L.") -> dict:
        response = await client.post("/api/suppliers", json={"name": name}, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture
def make_invoice(client: AsyncClient) -> Callable[..., dict]:
    async def _make(headers: dict[str, str], supplier_id: int, **overrides: Any) -> dict:
        payload = {
            "number": "INV-2026-0001",
            "supplier_id": supplier_id,
            "base_amount": "100.00",
            "tax_amount": "21.00",
            "total_amount": "121.00",
            "issue_date": "2026-03-15",
        }
        payload.update(overrides)
        response = await client.post("/api/invoices", json=payload, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


async def add_llm_call(
    db: AsyncSession, user_id: int, cost: str, created_at: datetime | None = None
) -> None:
    """Record a past call of the model costing `cost` USD, to set up a spending."""
    db.add(
        LlmCall(
            user_id=user_id,
            purpose="invoice_extraction",
            model="m",
            outcome="ok",
            input_tokens=1000,
            output_tokens=100,
            cost_usd=Decimal(cost),
            latency_ms=900,
            **({"created_at": created_at} if created_at else {}),
        )
    )
    await db.commit()


async def user_id_of(client: AsyncClient, headers: dict[str, str]) -> int:
    return (await client.get("/api/users/me", headers=headers)).json()["id"]
