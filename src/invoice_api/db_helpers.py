from collections.abc import Mapping
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
    constraint_details: Mapping[str, str] | None = None,
) -> None:
    """Commit, translating *expected* integrity errors into 409 Conflict.

    - UniqueViolation -> 409 with `unique_detail`, or with the entry of
      `constraint_details` for the violated constraint when a table has several.
    - ForeignKeyViolation -> 409 with `fk_detail` (if given).
    Any other error is re-raised: it is a real bug and should surface as a 500.
    """
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        cause = exc.orig
        if isinstance(cause, UniqueViolation):
            constraint = cause.diag.constraint_name
            raise_conflict((constraint_details or {}).get(constraint or "", unique_detail))
        if isinstance(cause, ForeignKeyViolation) and fk_detail is not None:
            raise_conflict(fk_detail)
        raise
