"""Turn an extracted invoice into stored rows for one user."""

from psycopg.errors import UniqueViolation
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_api.constants import INVOICE_DUPLICATE_DETAIL
from invoice_api.models import Category, Invoice, InvoiceStatus, Supplier
from invoice_api.models.invoice import INVOICE_NUMBER_UNIQUE
from invoice_api.models.supplier import SUPPLIER_NAME_MAX_LENGTH
from invoice_api.normalization import supplier_name_key
from invoice_api.schemas.extraction import ExtractedInvoice


class DuplicateInvoiceError(Exception):
    """This user already has an invoice with that number for that supplier."""


async def _find_supplier(
    db: AsyncSession, user_id: int, name: str, tax_id: str | None
) -> Supplier | None:
    """The user's supplier that this name / tax id refers to, if there is one.

    1. Same tax id: the same company, whatever the name says.
    2. Same normalised name ("ACME, S.L." is "Acme S.L."). If both sides have a
       tax id and they differ, they are different companies that share a name.
    """
    result = await db.scalars(
        select(Supplier).where(Supplier.user_id == user_id).order_by(Supplier.id)
    )
    suppliers = result.all()
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


async def _free_name(db: AsyncSession, user_id: int, name: str, tax_id: str | None) -> str:
    """Supplier names are unique per user. A different company (other tax id) with
    exactly the same name gets its tax id appended so both can exist."""
    taken = await db.scalar(
        select(Supplier.id).where(Supplier.user_id == user_id, Supplier.name == name)
    )
    if taken is None or tax_id is None:
        return name
    suffix = f" ({tax_id})"
    return name[: SUPPLIER_NAME_MAX_LENGTH - len(suffix)] + suffix


async def _create_supplier(
    db: AsyncSession, user_id: int, name: str, tax_id: str | None
) -> Supplier:
    try:
        # A savepoint, so a lost race only undoes this insert, not the request.
        async with db.begin_nested():
            supplier = Supplier(
                name=await _free_name(db, user_id, name, tax_id),
                tax_id=tax_id,
                user_id=user_id,
            )
            db.add(supplier)
    except IntegrityError:
        # Another request created it between our SELECT and INSERT: reuse it.
        # If it still is not there, the error was something else: re-raise.
        existing = await _find_supplier(db, user_id, name, tax_id)
        if existing is None:
            raise
        return existing
    return supplier


async def _learn_tax_id(db: AsyncSession, supplier: Supplier, tax_id: str) -> Supplier:
    """A supplier we only knew by name has now shown its tax id: remember it."""
    # Read now: the rollback below expires the supplier, and an expired attribute
    # cannot be reloaded implicitly in async code.
    supplier_id, user_id, name = supplier.id, supplier.user_id, supplier.name
    try:
        async with db.begin_nested():
            supplier.tax_id = tax_id
    except IntegrityError:
        # Lost a race: another request gave that tax id to another supplier.
        existing = await _find_supplier(db, user_id, name, tax_id)
        if existing is None or existing.id == supplier_id:
            raise
        return existing
    return supplier


async def _get_or_create_supplier(
    db: AsyncSession, user_id: int, name: str, tax_id: str | None
) -> Supplier:
    supplier = await _find_supplier(db, user_id, name, tax_id)
    if supplier is None:
        return await _create_supplier(db, user_id, name, tax_id)
    if tax_id is not None and supplier.tax_id is None:
        return await _learn_tax_id(db, supplier, tax_id)
    return supplier


async def _find_category_id(db: AsyncSession, user_id: int, name: str | None) -> int | None:
    if name is None:
        return None
    return await db.scalar(
        select(Category.id).where(Category.user_id == user_id, Category.name == name)
    )


async def create_invoice_from_extraction(
    db: AsyncSession, user_id: int, extracted: ExtractedInvoice
) -> Invoice:
    """Store the invoice (and its supplier, if new) in ONE transaction.

    Raises DuplicateInvoiceError if the number already exists for the supplier.
    """
    supplier = await _get_or_create_supplier(
        db, user_id, extracted.supplier_name, extracted.supplier_tax_id
    )
    invoice = Invoice(
        user_id=user_id,
        supplier_id=supplier.id,
        category_id=await _find_category_id(db, user_id, extracted.category_name),
        number=extracted.invoice_number,
        issue_date=extracted.issue_date,
        base_amount=extracted.base_amount,
        tax_amount=extracted.tax_amount,
        withholding_amount=extracted.withholding_amount,
        total_amount=extracted.total_amount,
        currency=extracted.currency,
        status=InvoiceStatus.PENDING,
    )
    db.add(invoice)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        cause = exc.orig
        if (
            isinstance(cause, UniqueViolation)
            and cause.diag.constraint_name == INVOICE_NUMBER_UNIQUE
        ):
            raise DuplicateInvoiceError(INVOICE_DUPLICATE_DETAIL) from exc
        raise
    return invoice
