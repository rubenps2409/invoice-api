from datetime import UTC, datetime, timedelta

import jwt

from invoice_api.config import settings
from invoice_api.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_verifies_the_original_password_only():
    hashed = hash_password("correct horse battery")

    assert verify_password("correct horse battery", hashed) is True
    assert verify_password("wrong password", hashed) is False


def test_hashing_is_salted():
    assert hash_password("same-password") != hash_password("same-password")


def test_verify_returns_false_for_a_stored_value_that_is_not_a_hash():
    assert verify_password("anything", "not-a-valid-hash") is False
    assert verify_password("anything", "") is False


def test_token_roundtrip():
    assert decode_access_token(create_access_token(42)) == 42


def test_token_expires_after_configured_minutes():
    token = create_access_token(1)

    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    remaining = datetime.fromtimestamp(payload["exp"], UTC) - datetime.now(UTC)

    max_lifetime = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    assert timedelta(0) < remaining <= max_lifetime


def test_decode_returns_none_for_garbage():
    assert decode_access_token("garbage") is None
