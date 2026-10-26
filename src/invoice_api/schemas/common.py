from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints

from invoice_api.constants import POSTGRES_INT_MAX
from invoice_api.models.invoice import INVOICE_AMOUNT_PRECISION, INVOICE_AMOUNT_SCALE
from invoice_api.normalization import normalize_tax_id


def _reject_nul(value: str) -> str:
    # PostgreSQL text cannot contain NUL
    if "\x00" in value:
        raise ValueError("must not contain NUL characters")
    return value


# Required text: stripped, no NUL, 1..N characters
Str100 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    AfterValidator(_reject_nul),
]
Str255 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
    AfterValidator(_reject_nul),
]


# Cap on what a client may send; separators are removed afterwards, so it is
# larger than SUPPLIER_TAX_ID_MAX_LENGTH, which applies to the normalised value.
_TAX_ID_INPUT_MAX_LENGTH = 50


def _valid_tax_id(value: str) -> str:
    tax_id = normalize_tax_id(value)
    if tax_id is None:
        raise ValueError("must be a valid tax id (NIF/CIF/VAT number)")
    return tax_id


# Tax id typed by a person: normalised, and rejected if it is not valid so the
# mistake is reported. (Model output uses a lenient variant that drops it.)
TaxId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=_TAX_ID_INPUT_MAX_LENGTH),
    AfterValidator(_valid_tax_id),
]

DbId = Annotated[int, Field(ge=1, le=POSTGRES_INT_MAX)]

# Same precision as the invoice columns. Negatives are allowed (credit notes)
Money = Annotated[
    Decimal,
    Field(
        max_digits=INVOICE_AMOUNT_PRECISION,
        decimal_places=INVOICE_AMOUNT_SCALE,
        allow_inf_nan=False,
    ),
]
