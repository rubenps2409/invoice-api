from invoice_api.models.base import Base
from sqlalchemy import String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from invoice_api.models.invoice import Invoice


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    invoices: Mapped[list["Invoice"]] = relationship(back_populates="category")

    __table_args__ = (UniqueConstraint("name", "user_id", name="uq_category_name_user_id"),)