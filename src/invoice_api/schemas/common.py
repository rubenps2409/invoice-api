from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints

from invoice_api.constants import POSTGRES_INT_MAX


def _reject_nul(value: str) -> str:
    # PostgreSQL text cannot contain NUL; psycopg would raise DataError (500).
    if "\x00" in value:
        raise ValueError("must not contain NUL characters")
    return value


# Required text: stripped, no NUL, 1..N characters.
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

DbId = Annotated[int, Field(ge=1, le=POSTGRES_INT_MAX)]

# Numeric(10, 2): up to 99,999,999.99. Negatives are allowed (credit notes).
Money = Annotated[
    Decimal, Field(max_digits=10, decimal_places=2, allow_inf_nan=False)
]
