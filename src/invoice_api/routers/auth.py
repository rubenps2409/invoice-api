from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from invoice_api.db_helpers import commit_or_conflict
from invoice_api.dependencies import DbSession
from invoice_api.models import User
from invoice_api.schemas.token import Token
from invoice_api.schemas.user import UserCreate, UserRead
from invoice_api.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL_TAKEN = "A user with this email already exists"
_INVALID_CREDENTIALS = "Incorrect email or password"

# Verified when the email is unknown, so both login failures take the same time.
_DUMMY_HASH = hash_password("not-a-real-password")


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: DbSession):
    user = User(email=data.email, hashed_password=hash_password(data.password))
    db.add(user)
    commit_or_conflict(db, unique_detail=_EMAIL_TAKEN)
    return user


@router.post("/login", response_model=Token)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession):
    email = form.username.strip().lower()
    user = db.scalar(select(User).where(User.email == email))

    hashed_password = user.hashed_password if user else _DUMMY_HASH
    password_ok = verify_password(form.password, hashed_password)
    if user is None or not password_ok:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            _INVALID_CREDENTIALS,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(user.id))
