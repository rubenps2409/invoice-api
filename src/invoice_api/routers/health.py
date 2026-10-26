from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from invoice_api.dependencies import DbSession
from invoice_api.schemas.health import HealthRead

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "",
    response_model=HealthRead,
    responses={503: {"description": "The database does not answer"}},
)
def read_health(db: DbSession):
    """Liveness plus database reachability. Public, and it never calls the model."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Database unavailable"
        ) from exc
    return HealthRead(status="ok")
