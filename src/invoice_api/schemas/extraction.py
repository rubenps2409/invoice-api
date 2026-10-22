from datetime import date
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from invoice_api.schemas.common import Money, Str100, Str255
from invoice_api.schemas.invoice import check_totals


class ExtractedInvoice(BaseModel):
    """Contract for what the LLM must return. If it does not validate, nothing
    is saved."""

    # Unknown keys are ignored: the service only reads the fields below.
    model_config = ConfigDict(extra="ignore")

    supplier_name: Str255
    invoice_number: Str100
    issue_date: date
    base_amount: Money
    tax_amount: Money
    total_amount: Money
    category_name: Str100 | None = None

    @model_validator(mode="after")
    def _totals_match(self) -> Self:
        check_totals(self.base_amount, self.tax_amount, self.total_amount)
        return self
