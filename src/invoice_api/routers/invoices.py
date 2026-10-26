from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select

from invoice_api.constants import DEFAULT_PAGE_SIZE, INVOICE_DUPLICATE_DETAIL
from invoice_api.db_helpers import commit_or_conflict
from invoice_api.dependencies import CurrentUserId, DbSession, IdPath, Limit, Skip
from invoice_api.models import Category, Invoice, InvoiceStatus, Supplier
from invoice_api.schemas.common import DbId
from invoice_api.schemas.invoice import (
    InvoiceCreate,
    InvoiceRead,
    InvoiceUpdate,
    check_amounts,
)

router = APIRouter(prefix="/invoices", tags=["invoices"])

_REFERENCE_REMOVED = "Supplier or category was removed, retry"
_UNPROCESSABLE = status.HTTP_422_UNPROCESSABLE_CONTENT


async def _get_owned_invoice(db: DbSession, invoice_id: int, user_id: int) -> Invoice:
    invoice = await db.scalar(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.user_id == user_id)
    )
    if invoice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    return invoice


async def _ensure_references(
    db: DbSession, user_id: int, supplier_id: int | None, category_id: int | None
) -> None:
    """Check that supplier/category exist AND belong to the user.

    Prevents linking invoices to other users' records and FK errors (500).
    """
    if (
        supplier_id is not None
        and await db.scalar(
            select(Supplier.id).where(Supplier.id == supplier_id, Supplier.user_id == user_id)
        )
        is None
    ):
        raise HTTPException(_UNPROCESSABLE, "supplier_id does not exist")
    if (
        category_id is not None
        and await db.scalar(
            select(Category.id).where(Category.id == category_id, Category.user_id == user_id)
        )
        is None
    ):
        raise HTTPException(_UNPROCESSABLE, "category_id does not exist")


@router.post("", response_model=InvoiceRead, status_code=status.HTTP_201_CREATED)
async def create_invoice(data: InvoiceCreate, db: DbSession, user_id: CurrentUserId):
    await _ensure_references(db, user_id, data.supplier_id, data.category_id)
    invoice = Invoice(**data.model_dump(), user_id=user_id)
    db.add(invoice)
    # The supplier/category may be deleted between the check and the commit.
    await commit_or_conflict(
        db,
        unique_detail=INVOICE_DUPLICATE_DETAIL,
        fk_detail=_REFERENCE_REMOVED,
    )
    return invoice


@router.get("", response_model=list[InvoiceRead])
async def list_invoices(
    db: DbSession,
    user_id: CurrentUserId,
    supplier_id: DbId | None = None,
    category_id: DbId | None = None,
    status_: Annotated[InvoiceStatus | None, Query(alias="status")] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    skip: Skip = 0,
    limit: Limit = DEFAULT_PAGE_SIZE,
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(_UNPROCESSABLE, "date_from must be <= date_to")

    stmt = select(Invoice).where(Invoice.user_id == user_id)
    if supplier_id is not None:
        stmt = stmt.where(Invoice.supplier_id == supplier_id)
    if category_id is not None:
        stmt = stmt.where(Invoice.category_id == category_id)
    if status_ is not None:
        stmt = stmt.where(Invoice.status == status_)
    if date_from is not None:
        stmt = stmt.where(Invoice.issue_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Invoice.issue_date <= date_to)
    # id as tie-breaker keeps the order deterministic, so pagination is stable.
    stmt = stmt.order_by(Invoice.issue_date.desc(), Invoice.id.desc())
    return (await db.scalars(stmt.offset(skip).limit(limit))).all()


@router.get("/{invoice_id}", response_model=InvoiceRead)
async def get_invoice(invoice_id: IdPath, db: DbSession, user_id: CurrentUserId):
    return await _get_owned_invoice(db, invoice_id, user_id)


@router.patch("/{invoice_id}", response_model=InvoiceRead)
async def update_invoice(
    invoice_id: IdPath, data: InvoiceUpdate, db: DbSession, user_id: CurrentUserId
):
    invoice = await _get_owned_invoice(db, invoice_id, user_id)
    changes = data.model_dump(exclude_unset=True)

    await _ensure_references(
        db,
        user_id,
        changes.get("supplier_id"),
        changes.get("category_id"),
    )

    # The schema only sees the request body; validate the merged state.
    try:
        check_amounts(
            changes.get("base_amount", invoice.base_amount),
            changes.get("tax_amount", invoice.tax_amount),
            changes.get("withholding_amount", invoice.withholding_amount),
            changes.get("total_amount", invoice.total_amount),
        )
    except ValueError as exc:
        raise HTTPException(_UNPROCESSABLE, str(exc)) from exc

    for field, value in changes.items():
        setattr(invoice, field, value)
    await commit_or_conflict(
        db,
        unique_detail=INVOICE_DUPLICATE_DETAIL,
        fk_detail=_REFERENCE_REMOVED,
    )
    return invoice


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(invoice_id: IdPath, db: DbSession, user_id: CurrentUserId):
    invoice = await _get_owned_invoice(db, invoice_id, user_id)
    await db.delete(invoice)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
