from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints

from invoice_api.constants import POSTGRES_INT_MAX
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


def _valid_tax_id(value: str) -> str:
    tax_id = normalize_tax_id(value)
    if tax_id is None:
        raise ValueError("must be a valid tax id (NIF/CIF/VAT number)")
    return tax_id


# Tax id typed by a person: normalised, and rejected if it is not valid so the
# mistake is reported. (Model output uses a lenient variant that drops it.)
TaxId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=50),
    AfterValidator(_valid_tax_id),
]

DbId = Annotated[int, Field(ge=1, le=POSTGRES_INT_MAX)]

# Numeric(10, 2): up to 99,999,999.99. Negatives are allowed (credit notes)
Money = Annotated[Decimal, Field(max_digits=10, decimal_places=2, allow_inf_nan=False)]
