"""Daily spending limits for the LLM extraction.

The spending is the estimated cost of the rows in llm_calls, which also hold the
failed attempts (they cost tokens too). A "day" is a UTC calendar day, so the
limit resets at 00:00 UTC and the time to wait is known exactly.
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_api.config import settings
from invoice_api.models import LlmCall


class UsageScope(StrEnum):
    USER = "user"
    GLOBAL = "global"


class UsageLimitExceeded(Exception):
    def __init__(self, scope: UsageScope, retry_after_seconds: int):
        super().__init__(f"{scope} daily budget reached")
        self.scope = scope
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class Usage:
    period_start: datetime
    resets_at: datetime
    spent_usd: Decimal
    calls: int


def _day(now: datetime) -> tuple[datetime, datetime]:
    """The UTC day that contains `now` (given in any time zone)."""
    now = now.astimezone(UTC)
    start = datetime(now.year, now.month, now.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


async def _spent(
    db: AsyncSession, start: datetime, end: datetime, user_id: int | None = None
) -> tuple[Decimal, int]:
    stmt = select(func.coalesce(func.sum(LlmCall.cost_usd), 0), func.count()).where(
        LlmCall.created_at >= start, LlmCall.created_at < end
    )
    if user_id is not None:
        stmt = stmt.where(LlmCall.user_id == user_id)
    spent, calls = (await db.execute(stmt)).one()
    return Decimal(spent), calls


async def usage_today(db: AsyncSession, user_id: int, now: datetime | None = None) -> Usage:
    """What the user has spent since 00:00 UTC."""
    start, end = _day(now or datetime.now(UTC))
    spent, calls = await _spent(db, start, end, user_id)
    return Usage(period_start=start, resets_at=end, spent_usd=spent, calls=calls)


async def check_budget(db: AsyncSession, user_id: int, now: datetime | None = None) -> None:
    """Raise UsageLimitExceeded if today's spending reached a limit.

    The global limit is checked first: when it is hit nobody can extract, whatever
    their own budget. The call that crosses a limit is still served, so the
    spending can overshoot by one extraction (and by a few under concurrency).
    """
    now = now or datetime.now(UTC)
    start, end = _day(now)
    retry_after = math.ceil((end - now.astimezone(UTC)).total_seconds())

    global_spent, _ = await _spent(db, start, end)
    if global_spent >= settings.GLOBAL_DAILY_BUDGET_USD:
        raise UsageLimitExceeded(UsageScope.GLOBAL, retry_after)

    user_spent, _ = await _spent(db, start, end, user_id)
    if user_spent >= settings.USER_DAILY_BUDGET_USD:
        raise UsageLimitExceeded(UsageScope.USER, retry_after)
