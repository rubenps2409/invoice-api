"""Turn an extracted invoice into stored rows for one user."""

from psycopg.errors import UniqueViolation
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from invoice_api.constants import INVOICE_DUPLICATE_DETAIL
from invoice_api.models import Category, Invoice, InvoiceStatus, Supplier
from invoice_api.models.invoice import INVOICE_NUMBER_UNIQUE
from invoice_api.models.supplier import SUPPLIER_NAME_MAX_LENGTH
from invoice_api.normalization import supplier_name_key
from invoice_api.schemas.extraction import ExtractedInvoice


class DuplicateInvoiceError(Exception):
    """This user already has an invoice with that number for that supplier."""


def _find_supplier(
    db: Session, user_id: int, name: str, tax_id: str | None
) -> Supplier | None:
    """The user's supplier that this name / tax id refers to, if there is one.

    1. Same tax id: the same company, whatever the name says.
    2. Same normalised name ("ACME, S.L." is "Acme S.L."). If both sides have a
       tax id and they differ, they are different companies that share a name.
    """
    suppliers = db.scalars(
        select(Supplier).where(Supplier.user_id == user_id).order_by(Supplier.id)
    ).all()
    if tax_id is not None:
        for supplier in suppliers:
            if supplier.tax_id == tax_id:
                return supplier

    key = supplier_name_key(name)
    for supplier in suppliers:
        if supplier_name_key(supplier.name) != key:
            continue
        if tax_id is not None and supplier.tax_id not in (None, tax_id):
            continue
        return supplier
    return None


def _free_name(db: Session, user_id: int, name: str, tax_id: str | None) -> str:
    """Supplier names are unique per user. A different company (other tax id) with
    exactly the same name gets its tax id appended so both can exist."""
    taken = db.scalar(
        select(Supplier.id).where(Supplier.user_id == user_id, Supplier.name == name)
    )
    if taken is None or tax_id is None:
        return name
    suffix = f" ({tax_id})"
    return name[: SUPPLIER_NAME_MAX_LENGTH - len(suffix)] + suffix


def _create_supplier(db: Session, user_id: int, name: str, tax_id: str | None) -> Supplier:
    try:
        # A savepoint, so a lost race only undoes this insert, not the request.
        with db.begin_nested():
            supplier = Supplier(
                name=_free_name(db, user_id, name, tax_id), tax_id=tax_id, user_id=user_id
            )
            db.add(supplier)
    except IntegrityError:
        # Another request created it between our SELECT and INSERT: reuse it.
        # If it still is not there, the error was something else: re-raise.
        existing = _find_supplier(db, user_id, name, tax_id)
        if existing is None:
            raise
        return existing
    return supplier


def _learn_tax_id(db: Session, supplier: Supplier, tax_id: str) -> Supplier:
    """A supplier we only knew by name has now shown its tax id: remember it."""
    try:
        with db.begin_nested():
            supplier.tax_id = tax_id
    except IntegrityError:
        # Lost a race: another request gave that tax id to another supplier.
        existing = _find_supplier(db, supplier.user_id, supplier.name, tax_id)
        if existing is None or existing.id == supplier.id:
            raise
        return existing
    return supplier


def _get_or_create_supplier(
    db: Session, user_id: int, name: str, tax_id: str | None
) -> Supplier:
    supplier = _find_supplier(db, user_id, name, tax_id)
    if supplier is None:
        return _create_supplier(db, user_id, name, tax_id)
    if tax_id is not None and supplier.tax_id is None:
        return _learn_tax_id(db, supplier, tax_id)
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
    supplier = _get_or_create_supplier(
        db, user_id, extracted.supplier_name, extracted.supplier_tax_id
    )
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
        cause = exc.orig
        if (
            isinstance(cause, UniqueViolation)
            and cause.diag.constraint_name == INVOICE_NUMBER_UNIQUE
        ):
            raise DuplicateInvoiceError(INVOICE_DUPLICATE_DETAIL) from exc
        raise
    return invoice
