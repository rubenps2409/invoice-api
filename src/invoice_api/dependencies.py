from typing import Annotated

from fastapi import Depends, Path
from sqlalchemy.orm import Session

from invoice_api.database import get_db


def get_current_user_id() -> int:
    """Usuario provisional. Se sustituye por el usuario autenticado en la semana 2."""
    return 1


DbSession = Annotated[Session, Depends(get_db)]
CurrentUserId = Annotated[int, Depends(get_current_user_id)]

POSTGRES_INT_MAX = 2_147_483_647

IdPath = Annotated[int, Path(ge=1, le=POSTGRES_INT_MAX)]