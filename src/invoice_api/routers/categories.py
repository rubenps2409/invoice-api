from typing import Annotated, NoReturn

from fastapi import APIRouter, HTTPException, Query, status
from psycopg.errors import ForeignKeyViolation, UniqueViolation
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from invoice_api.dependencies import CurrentUserId, DbSession, IdPath
from invoice_api.models.category import Category
from invoice_api.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate

router = APIRouter(prefix="/categories", tags=["categories"])


def _get_owned_category(db: Session, category_id: int, user_id: int) -> Category:
    category = db.scalar(
        select(Category).where(Category.id == category_id, Category.user_id == user_id)
    )
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    return category


def _raise_conflict() -> NoReturn:
    raise HTTPException(
        status.HTTP_409_CONFLICT, "A category with this name already exists"
    )


def _commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if isinstance(exc.orig, UniqueViolation):
            _raise_conflict()
        raise


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate, db: DbSession, user_id: CurrentUserId
) -> Category:
    category = Category(name=payload.name, user_id=user_id)
    db.add(category)
    _commit_or_conflict(db)
    return category


@router.get("", response_model=list[CategoryRead])
def list_categories(
    db: DbSession,
    user_id: CurrentUserId,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[Category]:
    stmt = (
        select(Category)
        .where(Category.user_id == user_id)
        .order_by(Category.id)
        .offset(skip)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


@router.get("/{category_id}", response_model=CategoryRead)
def get_category(category_id: IdPath, db: DbSession, user_id: CurrentUserId) -> Category:
    return _get_owned_category(db, category_id, user_id)


@router.put("/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: IdPath, payload: CategoryUpdate, db: DbSession, user_id: CurrentUserId
) -> Category:
    category = _get_owned_category(db, category_id, user_id)
    category.name = payload.name
    _commit_or_conflict(db)
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: IdPath, db: DbSession, user_id: CurrentUserId) -> None:
    category = _get_owned_category(db, category_id, user_id)
    db.delete(category)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if isinstance(exc.orig, ForeignKeyViolation):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Category has invoices and cannot be deleted",
            )
        raise