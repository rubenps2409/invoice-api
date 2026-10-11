from typing import NoReturn

from fastapi import HTTPException, status
from psycopg.errors import ForeignKeyViolation, UniqueViolation
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def raise_conflict(detail: str) -> NoReturn:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def commit_or_conflict(
    db: Session,
    *,
    unique_detail: str,
    fk_detail: str | None = None,
) -> None:
    """Hace commit traduciendo errores de integridad *esperables* a 409.

    - UniqueViolation -> 409 con `unique_detail`.
    - ForeignKeyViolation -> 409 con `fk_detail` (si se indica).
    Cualquier otro error se relanza: es un bug real y debe verse como 500.
    """
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        cause = exc.orig
        if isinstance(cause, UniqueViolation):
            raise_conflict(unique_detail)
        if isinstance(cause, ForeignKeyViolation) and fk_detail is not None:
            raise_conflict(fk_detail)
        raise
