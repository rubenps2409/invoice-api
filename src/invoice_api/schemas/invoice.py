from datetime import date, datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from invoice_api.models.invoice import InvoiceStatus
from invoice_api.schemas.common import Currency, DbId, Money, Str100

_NULLABLE = {"category_id"}
_DEFAULT_CURRENCY = "EUR"
# Invoices round their figures line by line, so the printed ones can be a cent
# apart. The tolerance is applied once, to the final comparison.
_TOTALS_TOLERANCE = Decimal("0.01")


def check_amounts(base: Decimal, tax: Decimal, withholding: Decimal, total: Decimal) -> None:
    """Raise ValueError unless the amounts are coherent.

    A credit note reverses EVERY amount, so base, tax and withholding are either
    all positive or all negative. Without this, a negative withholding would let
    any unmodelled extra amount (say, 45 of non-taxable expenses) be absorbed
    and still add up.
    """
    signs = {(amount > 0) - (amount < 0) for amount in (base, tax, withholding)} - {0}
    if len(signs) > 1:
        raise ValueError(
            "base_amount, tax_amount and withholding_amount must all be positive "
            "or all negative"
        )
    if abs(base + tax - withholding - total) > _TOTALS_TOLERANCE:
        raise ValueError(
            "total_amount must equal base_amount + tax_amount - withholding_amount"
        )


class InvoiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: Str100
    supplier_id: DbId
    category_id: DbId | None = None
    base_amount: Money
    tax_amount: Money
    withholding_amount: Money = Field(default=Decimal(0), validate_default=True)
    total_amount: Money
    currency: Currency = _DEFAULT_CURRENCY
    issue_date: date
    status: InvoiceStatus = InvoiceStatus.PENDING

    @model_validator(mode="after")
    def _totals_match(self) -> Self:
        check_amounts(
            self.base_amount, self.tax_amount, self.withholding_amount, self.total_amount
        )
        return self


class InvoiceUpdate(BaseModel):
    """PATCH payload: only the fields sent are updated."""

    model_config = ConfigDict(extra="forbid")

    number: Str100 | None = None
    supplier_id: DbId | None = None
    category_id: DbId | None = None  # explicit null clears the category
    base_amount: Money | None = None
    tax_amount: Money | None = None
    withholding_amount: Money | None = None
    total_amount: Money | None = None
    currency: Currency | None = None
    issue_date: date | None = None
    status: InvoiceStatus | None = None

    @model_validator(mode="after")
    def _validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        for name in self.model_fields_set - _NULLABLE:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        amounts = (
            self.base_amount,
            self.tax_amount,
            self.withholding_amount,
            self.total_amount,
        )
        # With a partial payload, the router checks against the stored values.
        if None not in amounts:
            check_amounts(*amounts)
        return self


class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    supplier_id: int
    category_id: int | None
    base_amount: Money
    tax_amount: Money
    withholding_amount: Money
    total_amount: Money
    currency: str
    issue_date: date
    status: InvoiceStatus
    created_at: datetime
