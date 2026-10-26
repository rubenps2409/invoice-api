from typing import Annotated

from fastapi import Depends, HTTPException, Path, Query, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from invoice_api.constants import BEARER_SCHEME, POSTGRES_INT_MAX
from invoice_api.database import get_db
from invoice_api.models import User
from invoice_api.security import decode_access_token

_MAX_PAGE_SIZE = 100

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
            headers={"WWW-Authenticate": BEARER_SCHEME},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_user_id(user: CurrentUser) -> int:
    return user.id


CurrentUserId = Annotated[int, Depends(get_current_user_id)]


def get_client_ip(request: Request) -> str:
    """The IP the server sees. Behind a proxy that is the proxy's, unless uvicorn
    runs with --proxy-headers and --forwarded-allow-ips set to the proxy: never
    read X-Forwarded-For here, any client could forge it."""
    return request.client.host if request.client else "unknown"


ClientIp = Annotated[str, Depends(get_client_ip)]

IdPath = Annotated[int, Path(ge=1, le=POSTGRES_INT_MAX)]

Skip = Annotated[int, Query(ge=0, le=POSTGRES_INT_MAX)]
Limit = Annotated[int, Query(ge=1, le=_MAX_PAGE_SIZE)]
