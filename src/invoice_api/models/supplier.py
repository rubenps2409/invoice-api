from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from invoice_api.models.base import Base

if TYPE_CHECKING:
    from invoice_api.models.invoice import Invoice


SUPPLIER_NAME_UNIQUE = "uq_supplier_name_user_id"
SUPPLIER_TAX_ID_UNIQUE = "uq_supplier_tax_id_user_id"
SUPPLIER_NAME_MAX_LENGTH = 255
SUPPLIER_TAX_ID_MAX_LENGTH = 20


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(SUPPLIER_NAME_MAX_LENGTH))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # Normalised NIF/CIF/VAT number (see normalization.normalize_tax_id). Optional:
    # PostgreSQL lets several suppliers of a user have none.
    tax_id: Mapped[str | None] = mapped_column(String(SUPPLIER_TAX_ID_MAX_LENGTH))

    invoices: Mapped[list["Invoice"]] = relationship(
        back_populates="supplier", passive_deletes="all"
    )

    __table_args__ = (
        UniqueConstraint("name", "user_id", name=SUPPLIER_NAME_UNIQUE),
        UniqueConstraint("tax_id", "user_id", name=SUPPLIER_TAX_ID_UNIQUE),
    )
