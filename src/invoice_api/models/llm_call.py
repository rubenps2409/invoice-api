from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from invoice_api.models.base import Base

LLM_CALL_USER_CREATED_INDEX = "ix_llm_calls_user_id_created_at"
LLM_CALL_CREATED_INDEX = "ix_llm_calls_created_at"
LLM_CALL_PURPOSE_MAX_LENGTH = 50
LLM_CALL_MODEL_MAX_LENGTH = 100
LLM_CALL_OUTCOME_MAX_LENGTH = 20
LLM_CALL_DETAIL_MAX_LENGTH = 255
# Estimated cost in USD. Calls cost fractions of a cent, hence the 8 decimals.
LLM_CALL_COST_PRECISION = 12
LLM_CALL_COST_SCALE = 8


class LlmCall(Base):
    """One call to an LLM, successful or not. Every call costs tokens, so
    failed attempts are recorded too."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    purpose: Mapped[str] = mapped_column(String(LLM_CALL_PURPOSE_MAX_LENGTH))
    model: Mapped[str] = mapped_column(String(LLM_CALL_MODEL_MAX_LENGTH))
    outcome: Mapped[str] = mapped_column(String(LLM_CALL_OUTCOME_MAX_LENGTH))
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    # Estimated from the configured prices. Calls cost fractions of a cent,
    # hence the 8 decimals.
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(LLM_CALL_COST_PRECISION, LLM_CALL_COST_SCALE)
    )
    latency_ms: Mapped[int]
    detail: Mapped[str | None] = mapped_column(String(LLM_CALL_DETAIL_MAX_LENGTH))

    __table_args__ = (
        # The daily budget sums the cost of a user (and of everybody) since midnight.
        Index(LLM_CALL_USER_CREATED_INDEX, "user_id", "created_at"),
        Index(LLM_CALL_CREATED_INDEX, "created_at"),
    )
