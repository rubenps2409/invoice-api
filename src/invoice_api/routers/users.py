from fastapi import APIRouter

from invoice_api.dependencies import CurrentUser
from invoice_api.schemas.user import UserRead

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
def read_current_user(user: CurrentUser):
    return user