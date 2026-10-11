from typing import Annotated

from fastapi import Depends, Path, Query
from sqlalchemy.orm import Session

from invoice_api.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, POSTGRES_INT_MAX
from invoice_api.database import get_db


def get_current_user_id() -> int:
    """Provisional: devuelve siempre el usuario 1. Se sustituye por JWT en la semana 2."""
    return 1


DbSession = Annotated[Session, Depends(get_db)]
CurrentUserId = Annotated[int, Depends(get_current_user_id)]

# Id en la ruta: rechaza 0, negativos y valores que desbordan INTEGER de Postgres.
IdPath = Annotated[int, Path(ge=1, le=POSTGRES_INT_MAX)]

# Paginación acotada: evita limit=10**9 y offsets que desbordan.
Skip = Annotated[int, Query(ge=0, le=POSTGRES_INT_MAX)]
Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
