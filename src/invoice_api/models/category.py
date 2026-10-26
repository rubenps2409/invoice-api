from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from invoice_api.models.base import Base

if TYPE_CHECKING:
    from invoice_api.models.invoice import Invoice

CATEGORY_NAME_UNIQUE = "uq_category_name_user_id"
CATEGORY_NAME_MAX_LENGTH = 100


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(CATEGORY_NAME_MAX_LENGTH))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    invoices: Mapped[list["Invoice"]] = relationship(
        back_populates="category", passive_deletes="all"
    )

    __table_args__ = (UniqueConstraint("name", "user_id", name=CATEGORY_NAME_UNIQUE),)
