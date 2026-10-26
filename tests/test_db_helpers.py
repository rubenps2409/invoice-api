from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import HTTPException
from psycopg.errors import ForeignKeyViolation, NotNullViolation, UniqueViolation
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_api.database import get_db
from invoice_api.db_helpers import commit_or_conflict


class FailingSession:
    """Minimal stand-in for a Session whose commit() raises a given DB error."""

    def __init__(self, error: Exception):
        self.error = error
        self.rolled_back = False

    async def commit(self):
        raise IntegrityError("INSERT ...", {}, self.error)

    async def rollback(self):
        self.rolled_back = True


def _as_session(fake: FailingSession) -> AsyncSession:
    return cast(AsyncSession, fake)


async def test_unique_violation_becomes_409_and_rolls_back():
    session = FailingSession(UniqueViolation("dup"))

    with pytest.raises(HTTPException) as exc:
        await commit_or_conflict(_as_session(session), unique_detail="duplicate")

    assert exc.value.status_code == 409
    assert exc.value.detail == "duplicate"
    assert session.rolled_back


def unique_violation_of(constraint: str) -> UniqueViolation:
    class Named(UniqueViolation):
        diag = SimpleNamespace(constraint_name=constraint)  # type: ignore[assignment]

    return Named("dup")


@pytest.mark.parametrize(
    ("violated", "expected"),
    [("uq_tax", "tax id taken"), ("uq_other", "duplicate"), ("", "duplicate")],
    ids=["mapped-constraint", "unmapped-constraint", "unknown-constraint"],
)
async def test_each_unique_constraint_can_have_its_own_message(violated, expected):
    session = FailingSession(unique_violation_of(violated))

    with pytest.raises(HTTPException) as exc:
        await commit_or_conflict(
            _as_session(session),
            unique_detail="duplicate",
            constraint_details={"uq_tax": "tax id taken"},
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == expected
    assert session.rolled_back


async def test_foreign_key_violation_becomes_409_when_a_detail_is_given():
    session = FailingSession(ForeignKeyViolation("fk"))

    with pytest.raises(HTTPException) as exc:
        await commit_or_conflict(
            _as_session(session), unique_detail="duplicate", fk_detail="in use"
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "in use"


@pytest.mark.parametrize(
    "error",
    [ForeignKeyViolation("fk"), NotNullViolation("null")],
    ids=["fk-without-detail", "unexpected-integrity-error"],
)
async def test_unexpected_integrity_errors_are_not_swallowed(error):
    session = FailingSession(error)

    with pytest.raises(IntegrityError):
        await commit_or_conflict(_as_session(session), unique_detail="duplicate")

    assert session.rolled_back


async def test_get_db_yields_a_session_and_closes_it():
    generator = get_db()

    session = await anext(generator)

    assert isinstance(session, AsyncSession)
    await generator.aclose()
