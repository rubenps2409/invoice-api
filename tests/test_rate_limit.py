"""Event counting per key and window."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from invoice_api.models import RateLimitEvent
from invoice_api.services.rate_limit import (
    RateLimitAction,
    RateLimitExceeded,
    check,
    hash_key,
    record,
)

NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
WINDOW = timedelta(minutes=15)
LOGIN = RateLimitAction.LOGIN_FAILED
KEY = hash_key("1.2.3.4", "ana@example.com")


def events(db):
    return db.scalars(select(RateLimitEvent).order_by(RateLimitEvent.id)).all()


def limit_check(db, key=KEY, action=LOGIN, limit=3, now=NOW):
    check(db, action, key, limit=limit, window=WINDOW, now=now)


# --- keys ---------------------------------------------------------------------


def test_a_key_is_a_fixed_length_hex_digest_and_is_stable():
    assert KEY == hash_key("1.2.3.4", "ana@example.com")
    assert len(KEY) == 64
    assert "ana" not in KEY and "1.2.3.4" not in KEY


def test_parts_cannot_be_shifted_to_collide():
    assert hash_key("a", "bc") != hash_key("ab", "c")


# --- counting -----------------------------------------------------------------


def test_below_the_limit_nothing_happens(db):
    record(db, LOGIN, KEY, now=NOW)
    record(db, LOGIN, KEY, now=NOW)

    limit_check(db)  # 2 events, limit 3: does not raise


def test_at_the_limit_the_next_attempt_is_stopped(db):
    for _ in range(3):
        record(db, LOGIN, KEY, now=NOW)

    with pytest.raises(RateLimitExceeded):
        limit_check(db)


def test_each_key_is_counted_on_its_own(db):
    for _ in range(3):
        record(db, LOGIN, KEY, now=NOW)

    limit_check(db, key=hash_key("1.2.3.4", "ben@example.com"))  # does not raise


def test_each_action_is_counted_on_its_own(db):
    for _ in range(3):
        record(db, LOGIN, KEY, now=NOW)

    limit_check(db, action=RateLimitAction.REGISTER)  # does not raise


def test_events_outside_the_window_do_not_count(db):
    for _ in range(3):
        record(db, LOGIN, KEY, now=NOW - WINDOW)  # exactly one window ago: out

    limit_check(db)  # does not raise


def test_one_key_can_be_recorded_with_several_hashes_at_once(db):
    other = hash_key("1.2.3.4")

    record(db, LOGIN, KEY, other, now=NOW)

    assert {e.key_hash for e in events(db)} == {KEY, other}


# --- how long to wait ---------------------------------------------------------


def test_the_wait_is_until_the_oldest_event_leaves_the_window(db):
    record(db, LOGIN, KEY, now=NOW - timedelta(minutes=10))  # leaves in 5 minutes
    record(db, LOGIN, KEY, now=NOW - timedelta(minutes=4))
    record(db, LOGIN, KEY, now=NOW - timedelta(minutes=1))

    with pytest.raises(RateLimitExceeded) as exc:
        limit_check(db)

    assert exc.value.retry_after_seconds == 300


def test_the_wait_is_at_least_one_second(db):
    almost_expired = NOW - WINDOW + timedelta(milliseconds=10)
    for _ in range(3):
        record(db, LOGIN, KEY, now=almost_expired)

    with pytest.raises(RateLimitExceeded) as exc:
        limit_check(db)

    assert exc.value.retry_after_seconds == 1


def test_once_the_wait_has_passed_the_key_is_free_again(db):
    for _ in range(3):
        record(db, LOGIN, KEY, now=NOW)
    with pytest.raises(RateLimitExceeded) as exc:
        limit_check(db)

    limit_check(db, now=NOW + timedelta(seconds=exc.value.retry_after_seconds))  # free


# --- storage ------------------------------------------------------------------


def test_only_the_hash_is_stored(db):
    record(db, LOGIN, KEY, now=NOW)

    (event,) = events(db)
    assert (event.action, event.key_hash, event.created_at) == ("login_failed", KEY, NOW)


def test_events_older_than_a_day_are_deleted_when_recording(db):
    record(db, LOGIN, KEY, now=NOW - timedelta(days=1, minutes=1))
    record(db, LOGIN, KEY, now=NOW - timedelta(hours=23))
    db.flush()

    record(db, LOGIN, KEY, now=NOW)
    db.flush()

    ages = sorted(NOW - e.created_at for e in events(db))
    assert ages == [timedelta(0), timedelta(hours=23)]
