from typing import Annotated

from fastapi import Depends, Path, Query
from sqlalchemy.orm import Session

from invoice_api.constants import MAX_PAGE_SIZE, POSTGRES_INT_MAX
from invoice_api.database import get_db


def get_current_user_id() -> int:
    """Placeholder: always returns user 1. To be replaced by JWT authentication."""
    return 1


DbSession = Annotated[Session, Depends(get_db)]
CurrentUserId = Annotated[int, Depends(get_current_user_id)]

IdPath = Annotated[int, Path(ge=1, le=POSTGRES_INT_MAX)]

Skip = Annotated[int, Query(ge=0, le=POSTGRES_INT_MAX)]
Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
