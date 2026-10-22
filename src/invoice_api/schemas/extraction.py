from datetime import date
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    field_validator,
    model_validator,
)

from invoice_api.config import settings
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


class ExtractionRequest(BaseModel):
    """Body of the extraction endpoint. The size limit bounds the cost of a call."""

    model_config = ConfigDict(extra="forbid")

    text: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=settings.MAX_INVOICE_TEXT_CHARS,
        ),
    ]

    @field_validator("text")
    @classmethod
    def _reject_nul(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("must not contain NUL characters")
        return value
