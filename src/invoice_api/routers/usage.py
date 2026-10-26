from decimal import Decimal

from fastapi import APIRouter

from invoice_api.config import settings
from invoice_api.dependencies import CurrentUserId, DbSession
from invoice_api.schemas.usage import UsageRead
from invoice_api.services.usage_limits import usage_today

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("", response_model=UsageRead)
async def read_usage(db: DbSession, user_id: CurrentUserId):
    """How much of today's extraction budget the user has used."""
    usage = await usage_today(db, user_id)
    budget = settings.USER_DAILY_BUDGET_USD
    return UsageRead(
        period_start=usage.period_start,
        resets_at=usage.resets_at,
        calls=usage.calls,
        estimated_spent_usd=usage.spent_usd,
        budget_usd=budget,
        remaining_usd=max(budget - usage.spent_usd, Decimal(0)),
    )
