from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from invoice_api.models.base import Base

USER_EMAIL_UNIQUE = "uq_users_email"
USER_EMAIL_MAX_LENGTH = 255
USER_HASHED_PASSWORD_MAX_LENGTH = 255


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(USER_EMAIL_MAX_LENGTH))
    hashed_password: Mapped[str] = mapped_column(String(USER_HASHED_PASSWORD_MAX_LENGTH))

    __table_args__ = (UniqueConstraint("email", name=USER_EMAIL_UNIQUE),)
