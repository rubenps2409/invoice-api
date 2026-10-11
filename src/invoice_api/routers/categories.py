from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from invoice_api.db_helpers import commit_or_conflict
from invoice_api.dependencies import CurrentUserId, DbSession, IdPath, Limit, Skip
from invoice_api.constants import DEFAULT_PAGE_SIZE
from invoice_api.models import Category
from invoice_api.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["categories"])

_DUPLICATE = "A category with this name already exists"
_IN_USE = "Category is used by invoices and cannot be deleted"


def _get_owned_category(db: DbSession, category_id: int, user_id: int) -> Category:
    """404 tanto si no existe como si es de otro usuario (no filtra existencia)."""
    category = db.scalar(
        select(Category).where(Category.id == category_id, Category.user_id == user_id)
    )
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    return category


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(data: CategoryCreate, db: DbSession, user_id: CurrentUserId):
    category = Category(**data.model_dump(), user_id=user_id)
    db.add(category)
    commit_or_conflict(db, unique_detail=_DUPLICATE)
    return category


@router.get("", response_model=list[CategoryRead])
def list_categories(
    db: DbSession,
    user_id: CurrentUserId,
    skip: Skip = 0,
    limit: Limit = DEFAULT_PAGE_SIZE,
):
    stmt = (
        select(Category)
        .where(Category.user_id == user_id)
        .order_by(Category.id)
        .offset(skip)
        .limit(limit)
    )
    return db.scalars(stmt).all()


@router.get("/{category_id}", response_model=CategoryRead)
def get_category(category_id: IdPath, db: DbSession, user_id: CurrentUserId):
    return _get_owned_category(db, category_id, user_id)


@router.put("/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: IdPath, data: CategoryUpdate, db: DbSession, user_id: CurrentUserId
):
    category = _get_owned_category(db, category_id, user_id)
    category.name = data.name
    commit_or_conflict(db, unique_detail=_DUPLICATE)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: IdPath, db: DbSession, user_id: CurrentUserId):
    category = _get_owned_category(db, category_id, user_id)
    db.delete(category)
    commit_or_conflict(db, unique_detail=_IN_USE, fk_detail=_IN_USE)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
