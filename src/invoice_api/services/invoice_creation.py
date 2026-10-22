"""Turn an extracted invoice into stored rows for one user."""

from psycopg.errors import UniqueViolation
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from invoice_api.models import Category, Invoice, InvoiceStatus, Supplier
from invoice_api.schemas.extraction import ExtractedInvoice


class DuplicateInvoiceError(Exception):
    """This user already has an invoice with that number for that supplier."""


def _find_supplier(db: Session, user_id: int, name: str) -> Supplier | None:
    # Case-insensitive, so "ACME S.L." reuses "Acme S.L." instead of cloning it.
    return db.scalars(
        select(Supplier)
        .where(Supplier.user_id == user_id, func.lower(Supplier.name) == name.lower())
        .order_by(Supplier.id)
    ).first()


def _get_or_create_supplier(db: Session, user_id: int, name: str) -> Supplier:
    supplier = _find_supplier(db, user_id, name)
    if supplier is not None:
        return supplier

    try:
        # A savepoint, so a lost race only undoes this insert, not the request.
        with db.begin_nested():
            supplier = Supplier(name=name, user_id=user_id)
            db.add(supplier)
    except IntegrityError:
        # Another request created it between our SELECT and INSERT: reuse it.
        # If it still is not there, the error was something else: re-raise.
        existing = _find_supplier(db, user_id, name)
        if existing is None:
            raise
        return existing
    return supplier


def _find_category_id(db: Session, user_id: int, name: str | None) -> int | None:
    if name is None:
        return None
    return db.scalar(
        select(Category.id).where(Category.user_id == user_id, Category.name == name)
    )


def create_invoice_from_extraction(
    db: Session, user_id: int, extracted: ExtractedInvoice
) -> Invoice:
    """Store the invoice (and its supplier, if new) in ONE transaction.

    Raises DuplicateInvoiceError if the number already exists for the supplier.
    """
    supplier = _get_or_create_supplier(db, user_id, extracted.supplier_name)
    invoice = Invoice(
        user_id=user_id,
        supplier_id=supplier.id,
        category_id=_find_category_id(db, user_id, extracted.category_name),
        number=extracted.invoice_number,
        issue_date=extracted.issue_date,
        base_amount=extracted.base_amount,
        tax_amount=extracted.tax_amount,
        total_amount=extracted.total_amount,
        status=InvoiceStatus.PENDING,
    )
    db.add(invoice)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if isinstance(exc.orig, UniqueViolation):
            raise DuplicateInvoiceError(
                "An invoice with this number already exists for this supplier"
            ) from exc
        raise
    return invoice
