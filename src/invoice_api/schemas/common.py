from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints

from invoice_api.constants import POSTGRES_INT_MAX


def _reject_nul(value: str) -> str:
    # PostgreSQL no admite el carácter NUL en texto: psycopg lanza DataError (500).
    if "\x00" in value:
        raise ValueError("must not contain NUL characters")
    return value


# Texto obligatorio: sin espacios en los extremos, sin NUL, longitud 1..N.
# Alias explícitos (no una función que devuelve un tipo) para que Pylance/Pyright
# los acepten como anotaciones de tipo.
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

# Id de clave foránea en un body/query: positivo y dentro del rango de INTEGER.
DbId = Annotated[int, Field(ge=1, le=POSTGRES_INT_MAX)]

# Numeric(10, 2): hasta 99.999.999,99. Se permiten negativos (abonos).
Money = Annotated[
    Decimal, Field(max_digits=10, decimal_places=2, allow_inf_nan=False)
]
