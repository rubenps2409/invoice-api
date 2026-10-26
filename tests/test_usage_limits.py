"""Daily spending limits, computed from the llm_calls log."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from invoice_api.config import settings
from invoice_api.models import LlmCall, User
from invoice_api.services.usage_limits import (
    UsageLimitExceeded,
    UsageScope,
    check_budget,
    usage_today,
)

NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
MIDNIGHT = datetime(2026, 3, 10, tzinfo=UTC)


@pytest.fixture(autouse=True)
def small_budgets(monkeypatch):
    monkeypatch.setattr(settings, "USER_DAILY_BUDGET_USD", Decimal("0.10"))
    monkeypatch.setattr(settings, "GLOBAL_DAILY_BUDGET_USD", Decimal("0.50"))


def make_user(db, email) -> User:
    user = User(email=email, hashed_password="x")
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def ana(db):
    return make_user(db, "ana@example.com")


@pytest.fixture
def ben(db):
    return make_user(db, "ben@example.com")


def spend(db, user, cost, at=NOW, outcome="ok"):
    db.add(
        LlmCall(
            user_id=user.id,
            created_at=at,
            purpose="invoice_extraction",
            model="m",
            outcome=outcome,
            input_tokens=1000,
            output_tokens=100,
            cost_usd=Decimal(cost),
            latency_ms=900,
        )
    )
    db.commit()


# --- what was spent ----------------------------------------------------------


def test_a_user_with_no_calls_has_spent_nothing(db, ana):
    usage = usage_today(db, ana.id, NOW)

    assert (usage.spent_usd, usage.calls) == (0, 0)
    assert usage.period_start == MIDNIGHT
    assert usage.resets_at == MIDNIGHT + timedelta(days=1)


def test_usage_adds_up_the_calls_of_the_day(db, ana):
    spend(db, ana, "0.01")
    spend(db, ana, "0.02")

    usage = usage_today(db, ana.id, NOW)

    assert usage.spent_usd == Decimal("0.03")
    assert usage.calls == 2


def test_failed_attempts_count_because_they_cost_tokens(db, ana):
    spend(db, ana, "0.04", outcome="invalid_output")
    spend(db, ana, "0.04", outcome="ok")

    assert usage_today(db, ana.id, NOW).spent_usd == Decimal("0.08")


def test_usage_ignores_other_users(db, ana, ben):
    spend(db, ana, "0.01")
    spend(db, ben, "0.09")

    assert usage_today(db, ana.id, NOW).spent_usd == Decimal("0.01")


def test_the_day_starts_at_midnight_utc_and_ends_before_the_next(db, ana):
    spend(db, ana, "0.01", at=MIDNIGHT - timedelta(microseconds=1))  # yesterday
    spend(db, ana, "0.02", at=MIDNIGHT)  # first instant of today
    spend(db, ana, "0.04", at=MIDNIGHT + timedelta(days=1) - timedelta(microseconds=1))
    spend(db, ana, "0.08", at=MIDNIGHT + timedelta(days=1))  # tomorrow

    assert usage_today(db, ana.id, NOW).spent_usd == Decimal("0.06")


def test_the_day_is_the_utc_day_whatever_time_zone_is_given(db, ana):
    spend(db, ana, "0.01", at=datetime(2026, 3, 9, 23, 30, tzinfo=UTC))
    madrid_at_half_past_midnight = datetime(
        2026, 3, 10, 0, 30, tzinfo=timezone(timedelta(hours=1))
    )

    usage = usage_today(db, ana.id, madrid_at_half_past_midnight)  # 23:30 UTC on the 9th

    assert usage.period_start == datetime(2026, 3, 9, tzinfo=UTC)
    assert usage.spent_usd == Decimal("0.01")


def test_the_reset_crosses_month_and_year_boundaries(db, ana):
    usage = usage_today(db, ana.id, datetime(2026, 12, 31, 18, 0, tzinfo=UTC))

    assert usage.resets_at == datetime(2027, 1, 1, tzinfo=UTC)


# --- the budget --------------------------------------------------------------


def test_a_user_below_the_budget_may_extract(db, ana):
    spend(db, ana, "0.09")

    check_budget(db, ana.id, NOW)  # does not raise


def test_a_user_who_reached_the_budget_is_stopped(db, ana):
    spend(db, ana, "0.06")
    spend(db, ana, "0.04")  # exactly the budget

    with pytest.raises(UsageLimitExceeded) as exc:
        check_budget(db, ana.id, NOW)

    assert exc.value.scope == UsageScope.USER


def test_one_users_spending_does_not_stop_another(db, ana, ben):
    spend(db, ana, "0.20")

    check_budget(db, ben.id, NOW)  # does not raise


def test_yesterdays_spending_does_not_count(db, ana):
    spend(db, ana, "0.20", at=MIDNIGHT - timedelta(hours=1))

    check_budget(db, ana.id, NOW)  # does not raise


@pytest.mark.parametrize(
    ("now", "seconds"),
    [
        (datetime(2026, 3, 10, 22, 30, tzinfo=UTC), 5400),
        (datetime(2026, 3, 10, 0, 0, tzinfo=UTC), 86400),
        (datetime(2026, 3, 10, 23, 59, 59, 500000, tzinfo=UTC), 1),  # rounded up
    ],
)
def test_the_user_is_told_how_long_until_midnight_utc(db, ana, now, seconds):
    spend(db, ana, "0.20", at=now)

    with pytest.raises(UsageLimitExceeded) as exc:
        check_budget(db, ana.id, now)

    assert exc.value.retry_after_seconds == seconds


def test_the_global_budget_stops_everybody_even_with_nothing_spent(db, ana, ben):
    spend(db, ben, "0.50")

    with pytest.raises(UsageLimitExceeded) as exc:
        check_budget(db, ana.id, NOW)

    assert exc.value.scope == UsageScope.GLOBAL


def test_the_global_budget_adds_up_every_user(db, ana, ben):
    spend(db, ana, "0.09")
    spend(db, ben, "0.09")  # each below their own 0.10 budget...

    check_budget(db, ana.id, NOW)  # ...and below the 0.50 global one

    for i in range(4):  # 0.18 + 4 x 0.09 = 0.54
        spend(db, make_user(db, f"u{i}@example.com"), "0.09")

    with pytest.raises(UsageLimitExceeded) as exc:
        check_budget(db, ana.id, NOW)
    assert exc.value.scope == UsageScope.GLOBAL


def test_the_global_limit_is_reported_before_the_users_own(db, ana):
    spend(db, ana, "0.60")  # over both budgets

    with pytest.raises(UsageLimitExceeded) as exc:
        check_budget(db, ana.id, NOW)

    assert exc.value.scope == UsageScope.GLOBAL


def test_the_budgets_come_from_the_settings(db, ana, monkeypatch):
    spend(db, ana, "0.20")
    monkeypatch.setattr(settings, "USER_DAILY_BUDGET_USD", Decimal("1.00"))

    check_budget(db, ana.id, NOW)  # does not raise
