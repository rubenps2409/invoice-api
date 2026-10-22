from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from invoice_api.models.base import Base


class LlmCall(Base):
    """One call to an LLM, successful or not. Every call costs tokens, so
    failed attempts are recorded too."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    purpose: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    outcome: Mapped[str] = mapped_column(String(20))
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    # Estimated from the configured prices. Calls cost fractions of a cent,
    # hence the 8 decimals.
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 8))
    latency_ms: Mapped[int]
    detail: Mapped[str | None] = mapped_column(String(255))
