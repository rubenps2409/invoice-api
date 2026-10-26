"""A cap on how many model calls are in flight at once in this process.

Waiting for the model is cheap now that the app is async, but not free: every call
holds an open HTTP request to the provider, and a slow provider could pile up
hundreds of them. Past the cap a request is refused at once instead of queuing, so
the client learns to come back later and the server's memory stays bounded.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from invoice_api.config import settings


class TooManyInFlight(Exception):
    """Every slot is taken."""


class InFlightLimit:
    def __init__(self, limit: int):
        self._slots = asyncio.Semaphore(limit)

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        # No await between this check and the acquire below, so no other task can
        # take the last slot in between.
        if self._slots.locked():
            raise TooManyInFlight
        async with self._slots:
            yield


@lru_cache
def _limit() -> InFlightLimit:
    return InFlightLimit(settings.LLM_MAX_CONCURRENT_CALLS)


async def get_in_flight_limit() -> InFlightLimit:
    """FastAPI dependency; tests replace it with a small limit."""
    return _limit()
