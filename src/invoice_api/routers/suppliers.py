from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from invoice_api.db_helpers import commit_or_conflict
from invoice_api.dependencies import CurrentUserId, DbSession, IdPath, Limit, Skip
from invoice_api.constants import DEFAULT_PAGE_SIZE
from invoice_api.models import Supplier
from invoice_api.schemas.supplier import SupplierCreate, SupplierRead, SupplierUpdate

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

_DUPLICATE = "A supplier with this name already exists"
_IN_USE = "Supplier is used by invoices and cannot be deleted"


def _get_owned_supplier(db: DbSession, supplier_id: int, user_id: int) -> Supplier:
    """404 tanto si no existe como si es de otro usuario (no filtra existencia)."""
    supplier = db.scalar(
        select(Supplier).where(Supplier.id == supplier_id, Supplier.user_id == user_id)
    )
    if supplier is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supplier not found")
    return supplier


@router.post("", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
def create_supplier(data: SupplierCreate, db: DbSession, user_id: CurrentUserId):
    supplier = Supplier(**data.model_dump(), user_id=user_id)
    db.add(supplier)
    commit_or_conflict(db, unique_detail=_DUPLICATE)
    return supplier


@router.get("", response_model=list[SupplierRead])
def list_suppliers(
    db: DbSession,
    user_id: CurrentUserId,
    skip: Skip = 0,
    limit: Limit = DEFAULT_PAGE_SIZE,
):
    stmt = (
        select(Supplier)
        .where(Supplier.user_id == user_id)
        .order_by(Supplier.id)
        .offset(skip)
        .limit(limit)
    )
    return db.scalars(stmt).all()


@router.get("/{supplier_id}", response_model=SupplierRead)
def get_supplier(supplier_id: IdPath, db: DbSession, user_id: CurrentUserId):
    return _get_owned_supplier(db, supplier_id, user_id)


@router.put("/{supplier_id}", response_model=SupplierRead)
def update_supplier(
    supplier_id: IdPath, data: SupplierUpdate, db: DbSession, user_id: CurrentUserId
):
    supplier = _get_owned_supplier(db, supplier_id, user_id)
    supplier.name = data.name
    commit_or_conflict(db, unique_detail=_DUPLICATE)
    return supplier


@router.delete("/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_supplier(supplier_id: IdPath, db: DbSession, user_id: CurrentUserId):
    supplier = _get_owned_supplier(db, supplier_id, user_id)
    db.delete(supplier)
    commit_or_conflict(db, unique_detail=_IN_USE, fk_detail=_IN_USE)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
