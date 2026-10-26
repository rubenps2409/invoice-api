from decimal import Decimal

import pytest
from sqlalchemy import select

from invoice_api.config import settings
from invoice_api.models import LlmCall, User
from invoice_api.services.extraction import Attempt, AttemptOutcome
from invoice_api.services.llm_usage import estimate_cost_usd, record_attempts


def test_every_outcome_fits_the_column_and_is_stored_as_plain_text():
    assert all(len(outcome) <= LlmCall.outcome.type.length for outcome in AttemptOutcome)  # type: ignore[attr-defined]
    assert {str(o) for o in AttemptOutcome} == {
        "ok",
        "invalid_output",
        "timeout",
        "api_error",
    }


PRICES = {
    "input_price_per_mtok": Decimal("0.10"),
    "output_price_per_mtok": Decimal("0.50"),
}


# --- cost estimate ----------------------------------------------------------


def test_cost_is_tokens_times_price_per_million():
    # (1000 * 0.10 + 100 * 0.50) / 1_000_000 = 0.00015
    assert estimate_cost_usd(1000, 100, **PRICES) == Decimal("0.00015000")


def test_zero_tokens_cost_nothing():
    assert estimate_cost_usd(0, 0, **PRICES) == Decimal("0.00000000")


def test_output_tokens_are_priced_separately():
    only_input = estimate_cost_usd(1_000_000, 0, **PRICES)
    only_output = estimate_cost_usd(0, 1_000_000, **PRICES)

    assert only_input == Decimal("0.10000000")
    assert only_output == Decimal("0.50000000")


def test_cost_is_rounded_to_the_column_precision():
    cost = estimate_cost_usd(
        1,
        1,
        input_price_per_mtok=Decimal("0.123456789"),
        output_price_per_mtok=Decimal(0),
    )

    assert cost == Decimal("0.00000012")


# --- persistence ------------------------------------------------------------


@pytest.fixture
def user(db):
    row = User(email="llm@example.com", hashed_password="x")
    db.add(row)
    db.commit()
    return row


def test_one_row_is_stored_per_attempt(db, user):
    attempts = [
        Attempt(AttemptOutcome.INVALID_OUTPUT, 900, 40, 800, "total_amount: mismatch"),
        Attempt(AttemptOutcome.OK, 1000, 100, 1200),
    ]

    record_attempts(db, user.id, attempts, model="some-model")

    rows = db.scalars(select(LlmCall).order_by(LlmCall.id)).all()
    assert [r.outcome for r in rows] == [AttemptOutcome.INVALID_OUTPUT, AttemptOutcome.OK]
    first, second = rows
    assert first.user_id == user.id
    assert first.purpose == "invoice_extraction"
    assert first.model == "some-model"
    assert (first.input_tokens, first.output_tokens, first.latency_ms) == (900, 40, 800)
    assert first.detail == "total_amount: mismatch"
    assert second.detail is None
    assert second.created_at is not None


def test_cost_uses_the_configured_prices(db, user, monkeypatch):
    monkeypatch.setattr(settings, "LLM_INPUT_PRICE_PER_MTOK", Decimal(1))
    monkeypatch.setattr(settings, "LLM_OUTPUT_PRICE_PER_MTOK", Decimal(2))

    (call,) = record_attempts(db, user.id, [Attempt(AttemptOutcome.OK, 1000, 500)], model="m")

    assert call.cost_usd == Decimal("0.00200000")


def test_failed_attempts_without_tokens_are_recorded_with_zero_cost(db, user):
    (call,) = record_attempts(
        db,
        user.id,
        [Attempt(AttemptOutcome.TIMEOUT, latency_ms=30000, detail="request timed out")],
        model="m",
    )

    assert call.outcome == AttemptOutcome.TIMEOUT
    assert call.input_tokens == call.output_tokens == 0
    assert call.cost_usd == 0


def test_long_detail_is_truncated_to_fit_the_column(db, user):
    long_detail = "x" * 1000

    record_attempts(
        db, user.id, [Attempt(AttemptOutcome.INVALID_OUTPUT, 1, 1, 1, long_detail)], model="m"
    )

    stored = db.scalar(select(LlmCall.detail))
    assert stored is not None
    assert len(stored) == 255


def test_no_attempts_stores_nothing(db, user):
    assert record_attempts(db, user.id, [], model="m") == []
    assert db.scalars(select(LlmCall)).all() == []


def test_records_survive_a_later_rollback(db, user):
    record_attempts(db, user.id, [Attempt(AttemptOutcome.OK, 10, 5, 100)], model="m")

    db.rollback()  # e.g. the request fails afterwards

    assert len(db.scalars(select(LlmCall)).all()) == 1
