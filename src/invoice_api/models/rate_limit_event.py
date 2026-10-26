from datetime import datetime

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from invoice_api.models.base import Base

RATE_LIMIT_EVENT_LOOKUP_INDEX = "ix_rate_limit_events_action_key_hash_created_at"
RATE_LIMIT_EVENT_CREATED_INDEX = "ix_rate_limit_events_created_at"
RATE_LIMIT_EVENT_ACTION_MAX_LENGTH = 20
RATE_LIMIT_EVENT_KEY_HASH_LENGTH = 64  # a hex SHA-256


class RateLimitEvent(Base):
    """One counted event (a failed login, a registration), per hashed key.

    The key is a hash of the client IP and/or the email, so the table never
    holds either in clear.
    """

    __tablename__ = "rate_limit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(RATE_LIMIT_EVENT_ACTION_MAX_LENGTH))
    key_hash: Mapped[str] = mapped_column(String(RATE_LIMIT_EVENT_KEY_HASH_LENGTH))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(RATE_LIMIT_EVENT_LOOKUP_INDEX, "action", "key_hash", "created_at"),
        Index(RATE_LIMIT_EVENT_CREATED_INDEX, "created_at"),
    )
