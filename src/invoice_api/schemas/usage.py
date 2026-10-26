from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, PlainSerializer

from invoice_api.models.llm_call import LLM_CALL_COST_SCALE

_COST_STEP = Decimal(1).scaleb(-LLM_CALL_COST_SCALE)


def _to_cost_scale(value: Decimal) -> Decimal:
    # The decimals of the column that stores each call's cost.
    return value.quantize(_COST_STEP)


def _fixed_point(value: Decimal) -> str:
    # str(Decimal("0.00000000")) is "0E-8": valid JSON text, but not a number
    # most clients can read. Always write plain decimals.
    return format(value, "f")


UsdCost = Annotated[
    Decimal,
    AfterValidator(_to_cost_scale),
    PlainSerializer(_fixed_point, return_type=str, when_used="json"),
]


class UsageRead(BaseModel):
    """What the user has spent today (a UTC day). The costs are estimates made
    from the configured prices, not what the provider will invoice."""

    period_start: datetime
    resets_at: datetime
    calls: int
    estimated_spent_usd: UsdCost
    budget_usd: UsdCost
    remaining_usd: UsdCost
