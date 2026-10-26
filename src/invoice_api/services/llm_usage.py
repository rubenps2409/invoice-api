from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from invoice_api.config import settings
from invoice_api.models import LlmCall
from invoice_api.models.llm_call import LLM_CALL_COST_SCALE, LLM_CALL_DETAIL_MAX_LENGTH
from invoice_api.services.extraction import Attempt

_PER_MILLION = Decimal(1_000_000)
_COST_STEP = Decimal(1).scaleb(-LLM_CALL_COST_SCALE)  # smallest step of the column

_PURPOSE_INVOICE_EXTRACTION = "invoice_extraction"


def estimate_cost_usd(
    input_tokens: int,
    output_tokens: int,
    *,
    input_price_per_mtok: Decimal,
    output_price_per_mtok: Decimal,
) -> Decimal:
    cost = (
        Decimal(input_tokens) * input_price_per_mtok
        + Decimal(output_tokens) * output_price_per_mtok
    ) / _PER_MILLION
    return cost.quantize(_COST_STEP, rounding=ROUND_HALF_UP)


async def record_attempts(
    db: AsyncSession,
    user_id: int,
    attempts: Sequence[Attempt],
    *,
    model: str,
    purpose: str = _PURPOSE_INVOICE_EXTRACTION,
) -> list[LlmCall]:
    """Store one row per attempt and COMMIT.

    The commit is deliberate: the tokens were spent whether or not the rest of
    the request succeeds, so this log must survive a later rollback or error.
    """
    calls = [
        LlmCall(
            user_id=user_id,
            purpose=purpose,
            model=model,
            outcome=attempt.outcome,
            input_tokens=attempt.input_tokens,
            output_tokens=attempt.output_tokens,
            cost_usd=estimate_cost_usd(
                attempt.input_tokens,
                attempt.output_tokens,
                input_price_per_mtok=settings.LLM_INPUT_PRICE_PER_MTOK,
                output_price_per_mtok=settings.LLM_OUTPUT_PRICE_PER_MTOK,
            ),
            latency_ms=attempt.latency_ms,
            detail=attempt.detail[:LLM_CALL_DETAIL_MAX_LENGTH] if attempt.detail else None,
        )
        for attempt in attempts
    ]
    db.add_all(calls)
    await db.commit()
    return calls
