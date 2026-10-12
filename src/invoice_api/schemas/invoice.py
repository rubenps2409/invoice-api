from datetime import date, datetime
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from invoice_api.models.invoice import InvoiceStatus
from invoice_api.schemas.common import DbId, Money, Str100

_NOT_NULLABLE = ("number", "supplier_id", "base_amount", "tax_amount",
                 "total_amount", "issue_date", "status")


def check_totals(base: Decimal, tax: Decimal, total: Decimal) -> None:
    if base + tax != total:
        raise ValueError("total_amount must equal base_amount + tax_amount")


class InvoiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: Str100
    supplier_id: DbId
    category_id: DbId | None = None
    base_amount: Money
    tax_amount: Money
    total_amount: Money
    issue_date: date
    status: InvoiceStatus = InvoiceStatus.PENDING

    @model_validator(mode="after")
    def _totals_match(self) -> Self:
        check_totals(self.base_amount, self.tax_amount, self.total_amount)
        return self


class InvoiceUpdate(BaseModel):
    """PATCH payload: only the fields sent are updated."""

    model_config = ConfigDict(extra="forbid")

    number: Str100 | None = None
    supplier_id: DbId | None = None
    category_id: DbId | None = None  # explicit null clears the category
    base_amount: Money | None = None
    tax_amount: Money | None = None
    total_amount: Money | None = None
    issue_date: date | None = None
    status: InvoiceStatus | None = None

    @model_validator(mode="after")
    def _validate_patch(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        for name in _NOT_NULLABLE:
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        base, tax, total = self.base_amount, self.tax_amount, self.total_amount
        # With a partial payload, the router checks against the stored values.
        if base is not None and tax is not None and total is not None:
            check_totals(base, tax, total)
        return self


class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    number: str
    supplier_id: int
    category_id: int | None
    base_amount: Money
    tax_amount: Money
    total_amount: Money
    issue_date: date
    status: InvoiceStatus
    created_at: datetime
