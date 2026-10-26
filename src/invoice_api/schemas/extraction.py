from datetime import date
from decimal import Decimal
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from invoice_api.config import settings
from invoice_api.normalization import normalize_tax_id
from invoice_api.schemas.common import Currency, Money, Str100, Str255
from invoice_api.schemas.invoice import check_amounts


def _tax_id_or_none(value: object) -> str | None:
    return normalize_tax_id(value) if isinstance(value, str) else None


# The tax id only helps to recognise the supplier, so a malformed one is dropped
# (the supplier is then matched by name) instead of rejecting the whole invoice.
OptionalTaxId = Annotated[str | None, BeforeValidator(_tax_id_or_none)]


class ExtractedInvoice(BaseModel):
    """Contract for what the LLM must return. If it does not validate, nothing
    is saved."""

    # Unknown keys are ignored: the service only reads the fields below.
    model_config = ConfigDict(extra="ignore")

    supplier_name: Str255
    supplier_tax_id: OptionalTaxId = None
    invoice_number: Str100
    issue_date: date
    base_amount: Money
    tax_amount: Money
    # No withholding is by far the common case; if the model leaves it out when
    # the invoice has one, the totals check fails and nothing is saved.
    withholding_amount: Money = Field(default=Decimal(0), validate_default=True)
    total_amount: Money
    # Required: a currency is never assumed (a bare "$" could be many).
    currency: Currency
    category_name: Str100 | None = None

    @model_validator(mode="after")
    def _totals_match(self) -> Self:
        check_amounts(
            self.base_amount, self.tax_amount, self.withholding_amount, self.total_amount
        )
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
