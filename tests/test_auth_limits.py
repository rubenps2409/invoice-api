"""Abuse limits of /auth/login and /auth/register (counted per client IP)."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from invoice_api.config import settings
from invoice_api.main import app
from invoice_api.models import RateLimitEvent
from invoice_api.routers import auth
from invoice_api.services.rate_limit import RateLimitAction, hash_key, record
from tests.conftest import PASSWORD, create_user

LOGIN = "/api/auth/login"
REGISTER = "/api/auth/register"
TESTCLIENT_IP = "testclient"  # what Starlette's TestClient reports as the client IP


@pytest.fixture(autouse=True)
def small_limits(monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_MAX_FAILURES_PER_IP_AND_EMAIL", 3)
    monkeypatch.setattr(settings, "LOGIN_MAX_FAILURES_PER_IP", 5)
    monkeypatch.setattr(settings, "LOGIN_WINDOW_MINUTES", 15)
    monkeypatch.setattr(settings, "REGISTER_MAX_PER_IP", 3)
    monkeypatch.setattr(settings, "REGISTER_WINDOW_MINUTES", 60)


def login(client, email, password="wrong-password"):
    return client.post(LOGIN, data={"username": email, "password": password})


def register(client, email, password=PASSWORD):
    return client.post(REGISTER, json={"email": email, "password": password})


def events(db):
    return db.scalar(select(func.count()).select_from(RateLimitEvent))


# --- login --------------------------------------------------------------------


def test_failed_logins_are_stopped_after_the_limit(client):
    create_user(client, "ana@example.com")

    statuses = [login(client, "ana@example.com").status_code for _ in range(4)]

    assert statuses == [401, 401, 401, 429]


def test_the_lockout_says_how_long_to_wait(client):
    create_user(client, "ana@example.com")
    for _ in range(3):
        login(client, "ana@example.com")

    response = login(client, "ana@example.com")

    assert response.status_code == 429
    assert response.json()["detail"] == "Too many attempts, try again later"
    assert 1 <= int(response.headers["Retry-After"]) <= 15 * 60


def test_the_right_password_does_not_get_in_while_locked_out(client):
    create_user(client, "ana@example.com")
    for _ in range(3):
        login(client, "ana@example.com")

    assert login(client, "ana@example.com", PASSWORD).status_code == 429


def test_a_locked_out_client_does_not_cost_a_password_hash(client, monkeypatch):
    create_user(client, "ana@example.com")
    for _ in range(3):
        login(client, "ana@example.com")
    hashes = []
    real_verify = auth.verify_password
    monkeypatch.setattr(
        auth, "verify_password", lambda *args: hashes.append(1) or real_verify(*args)
    )

    login(client, "ana@example.com")

    assert hashes == []


def test_failing_on_an_unknown_email_counts_too_so_accounts_cannot_be_probed(client):
    statuses = [login(client, "nobody@example.com").status_code for _ in range(4)]

    assert statuses == [401, 401, 401, 429]


def test_successful_logins_are_never_counted(client):
    create_user(client, "ana@example.com")

    statuses = {login(client, "ana@example.com", PASSWORD).status_code for _ in range(10)}

    assert statuses == {200}


def test_locking_one_email_leaves_another_email_of_the_same_ip_usable(client):
    create_user(client, "ana@example.com")
    create_user(client, "ben@example.com")
    for _ in range(3):
        login(client, "ana@example.com")

    assert login(client, "ben@example.com", PASSWORD).status_code == 200


def test_the_ip_limit_covers_all_emails_together(client):
    create_user(client, "ben@example.com")
    for i in range(5):  # 5 failures spread over different emails: no pair reaches 3
        login(client, f"user{i}@example.com")

    assert login(client, "ben@example.com", PASSWORD).status_code == 429


def test_failures_from_another_ip_cannot_lock_someone_out(client, db):
    """The reason failures are counted per IP+email and not per email."""
    create_user(client, "ana@example.com")
    attacker = TestClient(app, client=("203.0.113.9", 50000))
    for _ in range(3):
        attacker.post(LOGIN, data={"username": "ana@example.com", "password": "x"})
    assert (
        attacker.post(LOGIN, data={"username": "ana@example.com", "password": "x"}).status_code
        == 429
    )

    assert login(client, "ana@example.com", PASSWORD).status_code == 200


def test_old_failures_are_forgotten(client, db):
    create_user(client, "ana@example.com")
    long_ago = datetime.now(UTC) - timedelta(minutes=16)
    for _ in range(3):
        record(
            db,
            RateLimitAction.LOGIN_FAILED,
            hash_key(TESTCLIENT_IP, "ana@example.com"),
            now=long_ago,
        )
    db.commit()

    assert login(client, "ana@example.com", PASSWORD).status_code == 200


def test_only_hashes_are_stored(client, db):
    create_user(client, "ana@example.com")

    login(client, "ana@example.com")

    stored = db.scalars(
        select(RateLimitEvent).where(RateLimitEvent.action == RateLimitAction.LOGIN_FAILED)
    ).all()
    assert len(stored) == 2  # per IP+email and per IP
    for event in stored:
        assert len(event.key_hash) == 64
        assert "ana" not in event.key_hash and TESTCLIENT_IP not in event.key_hash


# --- register -----------------------------------------------------------------


def test_registrations_from_one_ip_are_limited(client):
    statuses = [register(client, f"user{i}@example.com").status_code for i in range(4)]

    assert statuses == [201, 201, 201, 429]


def test_the_registration_limit_says_how_long_to_wait(client):
    for i in range(3):
        register(client, f"user{i}@example.com")

    response = register(client, "late@example.com")

    assert response.headers["Retry-After"].isdigit()
    assert 1 <= int(response.headers["Retry-After"]) <= 60 * 60


def test_a_rejected_registration_still_counts(client):
    register(client, "ana@example.com")

    statuses = [register(client, "ana@example.com").status_code for _ in range(3)]

    assert statuses == [409, 409, 429]


def test_a_malformed_registration_costs_nothing_and_is_not_counted(client, db):
    response = client.post(REGISTER, json={"email": "not-an-email", "password": PASSWORD})

    assert response.status_code == 422
    assert events(db) == 0


def test_another_ip_can_still_register(client):
    for i in range(3):
        register(client, f"user{i}@example.com")
    other = TestClient(app, client=("203.0.113.9", 50000))

    response = other.post(REGISTER, json={"email": "new@example.com", "password": PASSWORD})

    assert response.status_code == 201


def test_old_registrations_are_forgotten(client, db):
    long_ago = datetime.now(UTC) - timedelta(minutes=61)
    for _ in range(3):
        record(db, RateLimitAction.REGISTER, hash_key(TESTCLIENT_IP), now=long_ago)
    db.commit()

    assert register(client, "ana@example.com").status_code == 201


def test_registering_and_failing_to_log_in_are_counted_separately(client):
    for i in range(3):
        register(client, f"user{i}@example.com")

    assert login(client, "user0@example.com", PASSWORD).status_code == 200
