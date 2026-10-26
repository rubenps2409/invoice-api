from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_api.config import settings
from invoice_api.constants import BEARER_SCHEME
from invoice_api.db_helpers import commit_or_conflict
from invoice_api.dependencies import ClientIp, DbSession
from invoice_api.http_helpers import retry_later
from invoice_api.models import User
from invoice_api.schemas.token import Token
from invoice_api.schemas.user import UserCreate, UserRead
from invoice_api.security import (
    create_access_token,
    hash_password,
    hash_password_async,
    verify_password_async,
)
from invoice_api.services.rate_limit import (
    RateLimitAction,
    RateLimitExceeded,
    check,
    hash_key,
    record,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL_TAKEN = "A user with this email already exists"
_INVALID_CREDENTIALS = "Incorrect email or password"
_TOO_MANY_ATTEMPTS = "Too many attempts, try again later"

# Verified when the email is unknown, so both login failures take the same time.
_DUMMY_HASH = hash_password("not-a-real-password")


async def _enforce(
    db: AsyncSession,
    action: RateLimitAction,
    key_hash: str,
    *,
    limit: int,
    window_minutes: int,
) -> None:
    try:
        await check(
            db, action, key_hash, limit=limit, window=timedelta(minutes=window_minutes)
        )
    except RateLimitExceeded as exc:
        raise retry_later(
            status.HTTP_429_TOO_MANY_REQUESTS, _TOO_MANY_ATTEMPTS, exc.retry_after_seconds
        ) from exc


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    responses={429: {"description": "Too many registrations from this IP"}},
)
async def register(data: UserCreate, db: DbSession, ip: ClientIp):
    key = hash_key(ip)
    await _enforce(
        db,
        RateLimitAction.REGISTER,
        key,
        limit=settings.REGISTER_MAX_PER_IP,
        window_minutes=settings.REGISTER_WINDOW_MINUTES,
    )
    # Counted before creating the user and committed on its own, so an attempt
    # that is rejected (say, an email already taken) still counts.
    await record(db, RateLimitAction.REGISTER, key)
    await db.commit()

    user = User(email=data.email, hashed_password=await hash_password_async(data.password))
    db.add(user)
    await commit_or_conflict(db, unique_detail=_EMAIL_TAKEN)
    return user


@router.post(
    "/login",
    response_model=Token,
    responses={429: {"description": "Too many failed attempts"}},
)
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession, ip: ClientIp
):
    email = form.username.strip().lower()
    # Failures are counted per IP+email and per IP. Counting by email alone would
    # let anyone lock somebody else out by failing on purpose with their email.
    pair_key, ip_key = hash_key(ip, email), hash_key(ip)
    # Checked before the password: a locked-out client must not cost an Argon2 hash.
    await _enforce(
        db,
        RateLimitAction.LOGIN_FAILED,
        pair_key,
        limit=settings.LOGIN_MAX_FAILURES_PER_IP_AND_EMAIL,
        window_minutes=settings.LOGIN_WINDOW_MINUTES,
    )
    await _enforce(
        db,
        RateLimitAction.LOGIN_FAILED,
        ip_key,
        limit=settings.LOGIN_MAX_FAILURES_PER_IP,
        window_minutes=settings.LOGIN_WINDOW_MINUTES,
    )

    user = await db.scalar(select(User).where(User.email == email))

    hashed_password = user.hashed_password if user else _DUMMY_HASH
    password_ok = await verify_password_async(form.password, hashed_password)
    if user is None or not password_ok:
        await record(db, RateLimitAction.LOGIN_FAILED, pair_key, ip_key)
        await db.commit()
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            _INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": BEARER_SCHEME},
        )
    return Token(access_token=create_access_token(user.id))
