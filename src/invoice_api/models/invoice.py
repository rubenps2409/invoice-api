from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from invoice_api.models.base import Base

if TYPE_CHECKING:
    from invoice_api.models.category import Category
    from invoice_api.models.supplier import Supplier

INVOICE_NUMBER_UNIQUE = "uq_invoice_user_supplier_number"
INVOICE_NUMBER_MAX_LENGTH = 100
INVOICE_STATUS_MAX_LENGTH = 20
INVOICE_CURRENCY_LENGTH = 3
# Amounts: up to 99,999,999.99
INVOICE_AMOUNT_PRECISION = 10
INVOICE_AMOUNT_SCALE = 2


class InvoiceStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    PARTIALLY_PAID = "partially_paid"
    CANCELLED = "cancelled"


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(INVOICE_NUMBER_MAX_LENGTH))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), index=True)

    base_amount: Mapped[Decimal] = mapped_column(
        Numeric(INVOICE_AMOUNT_PRECISION, INVOICE_AMOUNT_SCALE)
    )

    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(INVOICE_AMOUNT_PRECISION, INVOICE_AMOUNT_SCALE)
    )

    withholding_amount: Mapped[Decimal] = mapped_column(
        Numeric(INVOICE_AMOUNT_PRECISION, INVOICE_AMOUNT_SCALE)
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(INVOICE_AMOUNT_PRECISION, INVOICE_AMOUNT_SCALE)
    )

    currency: Mapped[str] = mapped_column(String(INVOICE_CURRENCY_LENGTH))
    issue_date: Mapped[date] = mapped_column(Date)
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(
            InvoiceStatus,
            native_enum=False,
            length=INVOICE_STATUS_MAX_LENGTH,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=InvoiceStatus.PENDING,
    )

    supplier: Mapped["Supplier"] = relationship(back_populates="invoices", lazy="raise")
    category: Mapped["Category | None"] = relationship(back_populates="invoices", lazy="raise")

    __table_args__ = (
        UniqueConstraint("user_id", "supplier_id", "number", name=INVOICE_NUMBER_UNIQUE),
    )
