from typing import Annotated

from fastapi import Depends, HTTPException, Path, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from invoice_api.constants import MAX_PAGE_SIZE, POSTGRES_INT_MAX
from invoice_api.database import get_db
from invoice_api.models import User
from invoice_api.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

DbSession = Annotated[Session, Depends(get_db)]

AccessToken = Annotated[str, Depends(oauth2_scheme)]


def get_current_user(token: AccessToken, db: DbSession) -> User:
    user_id = decode_access_token(token)
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_user_id(user: CurrentUser) -> int:
    return user.id


CurrentUserId = Annotated[int, Depends(get_current_user_id)]

IdPath = Annotated[int, Path(ge=1, le=POSTGRES_INT_MAX)]

Skip = Annotated[int, Query(ge=0, le=POSTGRES_INT_MAX)]
Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
