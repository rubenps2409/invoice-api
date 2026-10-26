"""Counting of events per key in a time window (failed logins, registrations).

Events live in the database, so the limits work across processes and survive a
restart, without any extra infrastructure. Keys are stored hashed: the table
never holds an IP or an email in clear.
"""

import hashlib
import math
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_api.constants import RATE_LIMIT_MAX_WINDOW_MINUTES
from invoice_api.models import RateLimitEvent


class RateLimitAction(StrEnum):
    LOGIN_FAILED = "login_failed"
    REGISTER = "register"


class RateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: int):
        super().__init__("rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds


def hash_key(*parts: str) -> str:
    """A fixed-length key for the given parts, e.g. an IP and an email."""
    # A separator that cannot appear in an IP or an email, so ("a", "bc") and
    # ("ab", "c") do not collide.
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


async def check(
    db: AsyncSession,
    action: RateLimitAction,
    key_hash: str,
    *,
    limit: int,
    window: timedelta,
    now: datetime | None = None,
) -> None:
    """Raise RateLimitExceeded if the key already has `limit` events in the window."""
    now = now or datetime.now(UTC)
    result = await db.execute(
        select(func.count(), func.min(RateLimitEvent.created_at)).where(
            RateLimitEvent.action == action,
            RateLimitEvent.key_hash == key_hash,
            RateLimitEvent.created_at > now - window,
        )
    )
    count, oldest = result.one()
    if count >= limit:
        # Allowed again when the oldest event of the window falls out of it.
        wait = math.ceil((oldest + window - now).total_seconds())
        raise RateLimitExceeded(max(wait, 1))


async def record(
    db: AsyncSession,
    action: RateLimitAction,
    *key_hashes: str,
    now: datetime | None = None,
) -> None:
    """Count one event for each key. The caller commits."""
    now = now or datetime.now(UTC)
    db.add_all(
        RateLimitEvent(action=action, key_hash=key_hash, created_at=now)
        for key_hash in key_hashes
    )
    # Older events can never matter again: no window is longer than a day.
    expired = now - timedelta(minutes=RATE_LIMIT_MAX_WINDOW_MINUTES)
    await db.execute(delete(RateLimitEvent).where(RateLimitEvent.created_at < expired))
