from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import select

from invoice_api.config import settings
from invoice_api.main import app
from invoice_api.models import User
from tests.conftest import PASSWORD, create_user, login_headers

EMAIL = "ana@example.com"


# --- register ---------------------------------------------------------------


async def test_register_returns_user_without_password(client):
    response = await client.post(
        "/api/auth/register", json={"email": EMAIL, "password": PASSWORD}
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == EMAIL
    assert isinstance(body["id"], int)
    assert "password" not in body
    assert "hashed_password" not in body


async def test_register_stores_a_hash_not_the_password(client, db):
    await create_user(client, EMAIL)

    user = await db.scalar(select(User).where(User.email == EMAIL))

    assert user.hashed_password != PASSWORD
    assert user.hashed_password.startswith("$argon2")


async def test_register_lowercases_email(client):
    user = await create_user(client, "Ana@Example.COM")

    assert user["email"] == EMAIL


async def test_register_duplicate_email_returns_409(client):
    await create_user(client, EMAIL)

    response = await client.post(
        "/api/auth/register", json={"email": EMAIL, "password": PASSWORD}
    )

    assert response.status_code == 409


async def test_register_duplicate_email_ignores_case(client):
    await create_user(client, EMAIL)

    response = await client.post(
        "/api/auth/register", json={"email": EMAIL.upper(), "password": PASSWORD}
    )

    assert response.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"email": EMAIL, "password": "short"},
        {"email": EMAIL, "password": "x" * 129},
        {"email": "not-an-email", "password": PASSWORD},
        {"email": EMAIL},
        {"password": PASSWORD},
        {"email": EMAIL, "password": PASSWORD, "is_admin": True},
    ],
    ids=[
        "password-too-short",
        "password-too-long",
        "invalid-email",
        "missing-password",
        "missing-email",
        "extra-field",
    ],
)
async def test_register_rejects_invalid_payload(client, payload):
    response = await client.post("/api/auth/register", json=payload)

    assert response.status_code == 422


# --- login ------------------------------------------------------------------


async def test_login_returns_bearer_token(client):
    await create_user(client, EMAIL)

    response = await client.post(
        "/api/auth/login", data={"username": EMAIL, "password": PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


async def test_login_ignores_email_case_and_surrounding_spaces(client):
    await create_user(client, EMAIL)

    response = await client.post(
        "/api/auth/login", data={"username": "  ANA@example.com ", "password": PASSWORD}
    )

    assert response.status_code == 200


async def test_login_failures_are_indistinguishable(client):
    await create_user(client, EMAIL)

    wrong_password = await client.post(
        "/api/auth/login", data={"username": EMAIL, "password": "wrong-password"}
    )
    unknown_email = await client.post(
        "/api/auth/login", data={"username": "nobody@example.com", "password": PASSWORD}
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.headers["WWW-Authenticate"] == "Bearer"


# --- /users/me --------------------------------------------------------------


async def test_me_returns_current_user(client):
    created = await create_user(client, EMAIL)
    headers = await login_headers(client, EMAIL)

    response = await client.get("/api/users/me", headers=headers)

    assert response.status_code == 200
    assert response.json() == created


async def test_me_without_token_returns_401(client):
    response = await client.get("/api/users/me")

    assert response.status_code == 401


@pytest.mark.parametrize(
    "token",
    ["garbage", "a.b.c"],
    ids=["not-a-jwt", "malformed-jwt"],
)
async def test_me_with_invalid_token_returns_401(client, token):
    response = await client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_me_with_token_signed_with_other_key_returns_401(client):
    user = await create_user(client, EMAIL)
    forged = jwt.encode(
        {"sub": str(user["id"]), "exp": datetime.now(UTC) + timedelta(minutes=5)},
        "some-other-secret-key-that-is-long-enough",
        algorithm=settings.ALGORITHM,
    )

    response = await client.get("/api/users/me", headers={"Authorization": f"Bearer {forged}"})

    assert response.status_code == 401


async def test_me_with_expired_token_returns_401(client):
    user = await create_user(client, EMAIL)
    expired = jwt.encode(
        {"sub": str(user["id"]), "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    response = await client.get(
        "/api/users/me", headers={"Authorization": f"Bearer {expired}"}
    )

    assert response.status_code == 401


async def test_me_with_token_of_deleted_user_returns_401(client, db):
    await create_user(client, EMAIL)
    headers = await login_headers(client, EMAIL)
    await db.delete(await db.scalar(select(User).where(User.email == EMAIL)))
    await db.commit()

    response = await client.get("/api/users/me", headers=headers)

    assert response.status_code == 401


# --- token edge cases -------------------------------------------------------


def _signed(claims, key=None, algorithm=None):
    return jwt.encode(
        claims, key or settings.SECRET_KEY, algorithm=algorithm or settings.ALGORITHM
    )


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    "subject",
    ["abc", "0", "-1", "2147483648", "99999999999999999999"],
    ids=["not-a-number", "zero", "negative", "above-int-max", "huge"],
)
async def test_me_with_unusable_subject_returns_401(client, subject):
    exp = datetime.now(UTC) + timedelta(minutes=5)
    token = _signed({"sub": subject, "exp": exp})

    response = await client.get("/api/users/me", headers=_bearer(token))

    assert response.status_code == 401


async def test_me_with_token_missing_exp_returns_401(client):
    user = await create_user(client, EMAIL)
    token = _signed({"sub": str(user["id"])})

    response = await client.get("/api/users/me", headers=_bearer(token))

    assert response.status_code == 401


async def test_me_with_token_missing_sub_returns_401(client):
    token = _signed({"exp": datetime.now(UTC) + timedelta(minutes=5)})

    response = await client.get("/api/users/me", headers=_bearer(token))

    assert response.status_code == 401


async def test_me_rejects_token_using_another_algorithm(client):
    user = await create_user(client, EMAIL)
    exp = datetime.now(UTC) + timedelta(minutes=5)
    claims = {"sub": str(user["id"]), "exp": exp}

    hs512 = _signed(claims, algorithm="HS512")
    unsigned = jwt.encode(claims, None, algorithm="none")

    assert (await client.get("/api/users/me", headers=_bearer(hs512))).status_code == 401
    assert (await client.get("/api/users/me", headers=_bearer(unsigned))).status_code == 401


async def test_me_with_non_bearer_scheme_returns_401(client):
    response = await client.get("/api/users/me", headers={"Authorization": "Basic abc"})

    assert response.status_code == 401


# --- more register / login edge cases ---------------------------------------


@pytest.mark.parametrize("length", [8, 128])
async def test_register_accepts_password_length_boundaries(client, length):
    response = await client.post(
        "/api/auth/register",
        json={"email": EMAIL, "password": "x" * length},
    )

    assert response.status_code == 201


async def test_register_accepts_unicode_password_and_login_works(client):
    password = "contraseña🙂123"
    await create_user(client, EMAIL, password)

    response = await client.post(
        "/api/auth/login", data={"username": EMAIL, "password": password}
    )

    assert response.status_code == 200


async def test_login_with_very_long_password_returns_401(client):
    await create_user(client, EMAIL)

    response = await client.post(
        "/api/auth/login", data={"username": EMAIL, "password": "x" * 10_000}
    )

    assert response.status_code == 401


async def test_the_documented_token_url_is_the_real_login_route(client):
    """The token URL is written separately from the router prefixes; if they
    drift apart, the "Authorize" button of the API docs stops working."""
    schemes = app.openapi()["components"]["securitySchemes"]
    (scheme,) = schemes.values()

    assert "/" + scheme["flows"]["password"]["tokenUrl"].lstrip("/") == app.url_path_for(
        "login"
    )


async def test_login_requires_form_data_not_json(client):
    await create_user(client, EMAIL)

    response = await client.post(
        "/api/auth/login", json={"username": EMAIL, "password": PASSWORD}
    )

    assert response.status_code == 422
