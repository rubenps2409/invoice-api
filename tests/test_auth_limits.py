"""Abuse limits of /auth/login and /auth/register (counted per client IP)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from invoice_api.config import settings
from invoice_api.models import RateLimitEvent
from invoice_api.routers import auth
from invoice_api.services.rate_limit import RateLimitAction, hash_key, record
from tests.conftest import PASSWORD, create_user, make_client

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


async def login(client, email, password="wrong-password"):
    return await client.post(LOGIN, data={"username": email, "password": password})


async def register(client, email, password=PASSWORD):
    return await client.post(REGISTER, json={"email": email, "password": password})


async def events(db):
    return await db.scalar(select(func.count()).select_from(RateLimitEvent))


# --- login --------------------------------------------------------------------


async def test_failed_logins_are_stopped_after_the_limit(client):
    await create_user(client, "ana@example.com")

    statuses = [(await login(client, "ana@example.com")).status_code for _ in range(4)]

    assert statuses == [401, 401, 401, 429]


async def test_the_lockout_says_how_long_to_wait(client):
    await create_user(client, "ana@example.com")
    for _ in range(3):
        await login(client, "ana@example.com")

    response = await login(client, "ana@example.com")

    assert response.status_code == 429
    assert response.json()["detail"] == "Too many attempts, try again later"
    assert 1 <= int(response.headers["Retry-After"]) <= 15 * 60


async def test_the_right_password_does_not_get_in_while_locked_out(client):
    await create_user(client, "ana@example.com")
    for _ in range(3):
        await login(client, "ana@example.com")

    assert (await login(client, "ana@example.com", PASSWORD)).status_code == 429


async def test_a_locked_out_client_does_not_cost_a_password_hash(client, monkeypatch):
    await create_user(client, "ana@example.com")
    for _ in range(3):
        await login(client, "ana@example.com")
    hashes = []
    real_verify = auth.verify_password_async

    async def counting_verify(*args):
        hashes.append(1)
        return await real_verify(*args)

    monkeypatch.setattr(auth, "verify_password_async", counting_verify)

    await login(client, "ana@example.com")

    assert hashes == []


async def test_failing_on_an_unknown_email_counts_too_so_accounts_cannot_be_probed(client):
    statuses = [(await login(client, "nobody@example.com")).status_code for _ in range(4)]

    assert statuses == [401, 401, 401, 429]


async def test_successful_logins_are_never_counted(client):
    await create_user(client, "ana@example.com")

    statuses = {
        (await login(client, "ana@example.com", PASSWORD)).status_code for _ in range(10)
    }

    assert statuses == {200}


async def test_locking_one_email_leaves_another_email_of_the_same_ip_usable(client):
    await create_user(client, "ana@example.com")
    await create_user(client, "ben@example.com")
    for _ in range(3):
        await login(client, "ana@example.com")

    assert (await login(client, "ben@example.com", PASSWORD)).status_code == 200


async def test_the_ip_limit_covers_all_emails_together(client):
    await create_user(client, "ben@example.com")
    for i in range(5):  # 5 failures spread over different emails: no pair reaches 3
        await login(client, f"user{i}@example.com")

    assert (await login(client, "ben@example.com", PASSWORD)).status_code == 429


async def test_failures_from_another_ip_cannot_lock_someone_out(client, db):
    """The reason failures are counted per IP+email and not per email."""
    await create_user(client, "ana@example.com")
    async with make_client(("203.0.113.9", 50000)) as attacker:
        for _ in range(3):
            await attacker.post(LOGIN, data={"username": "ana@example.com", "password": "x"})
        blocked = await attacker.post(
            LOGIN, data={"username": "ana@example.com", "password": "x"}
        )
    assert blocked.status_code == 429

    assert (await login(client, "ana@example.com", PASSWORD)).status_code == 200


async def test_old_failures_are_forgotten(client, db):
    await create_user(client, "ana@example.com")
    long_ago = datetime.now(UTC) - timedelta(minutes=16)
    for _ in range(3):
        await record(
            db,
            RateLimitAction.LOGIN_FAILED,
            hash_key(TESTCLIENT_IP, "ana@example.com"),
            now=long_ago,
        )
    await db.commit()

    assert (await login(client, "ana@example.com", PASSWORD)).status_code == 200


async def test_only_hashes_are_stored(client, db):
    await create_user(client, "ana@example.com")

    await login(client, "ana@example.com")

    stored = (
        await db.scalars(
            select(RateLimitEvent).where(RateLimitEvent.action == RateLimitAction.LOGIN_FAILED)
        )
    ).all()
    assert len(stored) == 2  # per IP+email and per IP
    for event in stored:
        assert len(event.key_hash) == 64
        assert "ana" not in event.key_hash and TESTCLIENT_IP not in event.key_hash


# --- register -----------------------------------------------------------------


async def test_registrations_from_one_ip_are_limited(client):
    statuses = [(await register(client, f"user{i}@example.com")).status_code for i in range(4)]

    assert statuses == [201, 201, 201, 429]


async def test_the_registration_limit_says_how_long_to_wait(client):
    for i in range(3):
        await register(client, f"user{i}@example.com")

    response = await register(client, "late@example.com")

    assert response.headers["Retry-After"].isdigit()
    assert 1 <= int(response.headers["Retry-After"]) <= 60 * 60


async def test_a_rejected_registration_still_counts(client):
    await register(client, "ana@example.com")

    statuses = [(await register(client, "ana@example.com")).status_code for _ in range(3)]

    assert statuses == [409, 409, 429]


async def test_a_malformed_registration_costs_nothing_and_is_not_counted(client, db):
    response = await client.post(
        REGISTER, json={"email": "not-an-email", "password": PASSWORD}
    )

    assert response.status_code == 422
    assert await events(db) == 0


async def test_another_ip_can_still_register(client):
    for i in range(3):
        await register(client, f"user{i}@example.com")
    async with make_client(("203.0.113.9", 50000)) as other:
        response = await other.post(
            REGISTER, json={"email": "new@example.com", "password": PASSWORD}
        )

    assert response.status_code == 201


async def test_old_registrations_are_forgotten(client, db):
    long_ago = datetime.now(UTC) - timedelta(minutes=61)
    for _ in range(3):
        await record(db, RateLimitAction.REGISTER, hash_key(TESTCLIENT_IP), now=long_ago)
    await db.commit()

    assert (await register(client, "ana@example.com")).status_code == 201


async def test_registering_and_failing_to_log_in_are_counted_separately(client):
    for i in range(3):
        await register(client, f"user{i}@example.com")

    assert (await login(client, "user0@example.com", PASSWORD)).status_code == 200
