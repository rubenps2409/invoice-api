"""GET /api/usage: the user's spending against today's budget."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from invoice_api.config import settings
from tests.conftest import add_llm_call, user_id_of

URL = "/api/usage"


@pytest.fixture(autouse=True)
def budget(monkeypatch):
    monkeypatch.setattr(settings, "USER_DAILY_BUDGET_USD", Decimal("0.10"))


def midnight_utc() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def test_requires_authentication(client):
    assert client.get(URL).status_code == 401


def test_a_new_user_has_spent_nothing(client, headers_a):
    body = client.get(URL, headers=headers_a).json()

    assert body["calls"] == 0
    assert body["estimated_spent_usd"] == "0.00000000"
    assert body["budget_usd"] == "0.10000000"
    assert body["remaining_usd"] == "0.10000000"


def test_the_period_is_the_current_utc_day(client, headers_a):
    body = client.get(URL, headers=headers_a).json()

    start = datetime.fromisoformat(body["period_start"])
    resets = datetime.fromisoformat(body["resets_at"])
    assert start == midnight_utc()
    assert resets - start == timedelta(days=1)


def test_spending_is_added_up_and_taken_from_the_budget(client, db, headers_a):
    me = user_id_of(client, headers_a)
    add_llm_call(db, me, "0.02")
    add_llm_call(db, me, "0.03")

    body = client.get(URL, headers=headers_a).json()

    assert body["calls"] == 2
    assert body["estimated_spent_usd"] == "0.05000000"
    assert body["remaining_usd"] == "0.05000000"


def test_the_remaining_budget_is_never_negative(client, db, headers_a):
    add_llm_call(db, user_id_of(client, headers_a), "0.40")

    body = client.get(URL, headers=headers_a).json()

    assert body["estimated_spent_usd"] == "0.40000000"
    assert body["remaining_usd"] == "0.00000000"


def test_only_the_users_own_spending_today_is_counted(client, db, headers_a, headers_b):
    add_llm_call(db, user_id_of(client, headers_a), "0.01")
    add_llm_call(db, user_id_of(client, headers_b), "0.07")
    add_llm_call(
        db,
        user_id_of(client, headers_a),
        "0.09",
        created_at=midnight_utc() - timedelta(hours=1),
    )

    body = client.get(URL, headers=headers_a).json()

    assert (body["calls"], body["estimated_spent_usd"]) == (1, "0.01000000")


def test_it_does_not_reveal_the_services_total(client, db, headers_a, headers_b):
    add_llm_call(db, user_id_of(client, headers_b), "0.30")

    body = client.get(URL, headers=headers_a).json()

    assert set(body) == {
        "period_start",
        "resets_at",
        "calls",
        "estimated_spent_usd",
        "budget_usd",
        "remaining_usd",
    }


def test_it_matches_what_the_extraction_endpoint_enforces(client, db, headers_a):
    """When /usage says nothing is left, the extraction is refused."""
    add_llm_call(db, user_id_of(client, headers_a), "0.10")

    usage = client.get(URL, headers=headers_a).json()
    extraction = client.post(
        "/api/invoices/extract", json={"text": "Invoice 1 Total 121,00"}, headers=headers_a
    )

    assert usage["remaining_usd"] == "0.00000000"
    assert extraction.status_code in (429, 503)  # 503 if the key is not configured
