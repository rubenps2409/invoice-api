"""The cap on model calls in flight: past it, extraction is refused at once."""

import asyncio

import pytest

from invoice_api.main import app
from invoice_api.services.concurrency import (
    InFlightLimit,
    TooManyInFlight,
    get_in_flight_limit,
)
from invoice_api.services.extraction import ExtractionTimeout, get_extractor
from tests.test_extract_endpoint import TEXT, URL, FakeExtractor, llm_calls, succeed

# --- the limit itself -------------------------------------------------------------


async def test_slots_up_to_the_limit_are_granted():
    limit = InFlightLimit(2)

    async with limit.slot(), limit.slot():
        pass


async def test_a_call_past_the_limit_is_refused_without_waiting():
    limit = InFlightLimit(1)

    async with limit.slot():
        with pytest.raises(TooManyInFlight):
            async with limit.slot():
                pass


async def test_a_slot_is_freed_when_the_call_ends():
    limit = InFlightLimit(1)
    async with limit.slot():
        pass

    async with limit.slot():
        pass


async def test_a_slot_is_freed_when_the_call_fails():
    limit = InFlightLimit(1)
    with pytest.raises(RuntimeError):
        async with limit.slot():
            raise RuntimeError

    async with limit.slot():
        pass


# --- the endpoint -----------------------------------------------------------------


class GatedExtractor(FakeExtractor):
    """Blocks inside the model call until the test opens the gate."""

    def __init__(self, outcome):
        super().__init__(outcome)
        self.entered = asyncio.Event()
        self.gate = asyncio.Event()

    async def extract(self, text, categories=()):
        self.entered.set()
        await self.gate.wait()
        return await super().extract(text, categories)


@pytest.fixture
def one_slot():
    limit = InFlightLimit(1)
    app.dependency_overrides[get_in_flight_limit] = lambda: limit
    return limit


async def test_a_request_past_the_limit_gets_503_and_retry_after(client, headers_a, one_slot):
    extractor = GatedExtractor(succeed())
    app.dependency_overrides[get_extractor] = lambda: extractor
    first = asyncio.create_task(client.post(URL, json={"text": TEXT}, headers=headers_a))
    await extractor.entered.wait()

    refused = await client.post(URL, json={"text": TEXT}, headers=headers_a)
    extractor.gate.set()

    assert refused.status_code == 503
    assert refused.headers["Retry-After"] == "5"
    assert refused.json() == {"detail": "Invoice extraction is temporarily unavailable"}
    assert (await first).status_code == 201


async def test_a_refused_request_costs_nothing(client, db, headers_a, one_slot):
    extractor = GatedExtractor(succeed())
    app.dependency_overrides[get_extractor] = lambda: extractor
    first = asyncio.create_task(client.post(URL, json={"text": TEXT}, headers=headers_a))
    await extractor.entered.wait()

    await client.post(URL, json={"text": TEXT}, headers=headers_a)
    extractor.gate.set()
    await first

    # Only the first request called the model, so only it was recorded.
    assert len(await llm_calls(db)) == 1
    assert len(extractor.calls) == 1


async def test_the_slot_is_freed_after_a_failed_extraction(client, headers_a, one_slot):
    extractor = FakeExtractor(ExtractionTimeout("slow", []))
    app.dependency_overrides[get_extractor] = lambda: extractor
    failed = await client.post(URL, json={"text": TEXT}, headers=headers_a)

    extractor.outcome = succeed()
    retried = await client.post(URL, json={"text": TEXT}, headers=headers_a)

    assert failed.status_code == 504
    assert retried.status_code == 201
