"""The sample data is the first thing anyone sees, so it must be coherent."""

from decimal import Decimal

import pytest
from sqlalchemy import func, select

from invoice_api.models import Category, Invoice, InvoiceStatus, Supplier, User
from invoice_api.normalization import normalize_tax_id
from invoice_api.schemas.invoice import check_amounts
from scripts.seed import DEMO_EMAIL, INVOICE_COUNT, SUPPLIERS, seed


@pytest.fixture
async def seeded(db):
    await seed(db, reset=True)
    user = await db.scalar(select(User).where(User.email == DEMO_EMAIL))
    assert user is not None
    return db, user


async def invoices_of(db, user):
    return (await db.scalars(select(Invoice).where(Invoice.user_id == user.id))).all()


async def test_every_invoice_respects_the_totals_rule(seeded):
    db, user = seeded

    invoices = await invoices_of(db, user)

    assert len(invoices) == INVOICE_COUNT
    for invoice in invoices:
        check_amounts(
            invoice.base_amount,
            invoice.tax_amount,
            invoice.withholding_amount,
            invoice.total_amount,
        )


async def test_the_data_has_withholdings_foreign_currencies_and_credit_notes(seeded):
    db, user = seeded
    invoices = await invoices_of(db, user)

    assert any(i.withholding_amount > 0 for i in invoices)
    assert {"EUR", "USD", "GBP"} <= {i.currency for i in invoices}
    assert any(i.total_amount < 0 for i in invoices)


async def test_a_credit_note_reverses_every_amount(seeded):
    db, user = seeded

    for invoice in await invoices_of(db, user):
        if invoice.total_amount < 0:
            assert invoice.base_amount < 0
            assert invoice.tax_amount <= 0
            assert invoice.withholding_amount <= 0
            assert "-R-" in invoice.number


async def test_withholding_only_appears_for_suppliers_that_apply_it(seeded):
    db, user = seeded
    applies = {s.name for s in SUPPLIERS if s.withholding_rate}
    suppliers = {s.id: s.name for s in await db.scalars(select(Supplier))}

    for invoice in await invoices_of(db, user):
        has_withholding = invoice.withholding_amount != 0
        assert has_withholding == (suppliers[invoice.supplier_id] in applies)


async def test_each_invoice_uses_its_suppliers_currency(seeded):
    db, user = seeded
    currency = {s.name: s.currency for s in SUPPLIERS}
    suppliers = {s.id: s.name for s in await db.scalars(select(Supplier))}

    for invoice in await invoices_of(db, user):
        assert invoice.currency == currency[suppliers[invoice.supplier_id]]


async def test_tax_ids_are_valid_and_some_suppliers_have_none(seeded):
    db, user = seeded
    suppliers = (await db.scalars(select(Supplier).where(Supplier.user_id == user.id))).all()

    tax_ids = [s.tax_id for s in suppliers if s.tax_id]
    assert all(normalize_tax_id(t) == t for t in tax_ids)
    assert len(set(tax_ids)) == len(tax_ids)
    assert any(s.tax_id is None for s in suppliers)


async def test_old_invoices_are_mostly_settled_and_recent_ones_pending(seeded):
    db, user = seeded
    invoices = await invoices_of(db, user)
    oldest = sorted(invoices, key=lambda i: i.issue_date)[: INVOICE_COUNT // 2]
    newest = sorted(invoices, key=lambda i: i.issue_date)[INVOICE_COUNT // 2 :]

    def share(items, status):
        return sum(i.status == status for i in items) / len(items)

    assert share(oldest, InvoiceStatus.PAID) > share(newest, InvoiceStatus.PAID)
    assert share(newest, InvoiceStatus.PENDING) > share(oldest, InvoiceStatus.PENDING)


async def test_amounts_are_exact_cents(seeded):
    db, user = seeded

    for invoice in await invoices_of(db, user):
        for amount in (invoice.base_amount, invoice.tax_amount, invoice.total_amount):
            assert amount == amount.quantize(Decimal("0.01"))


async def test_running_it_again_adds_nothing(seeded):
    db, user = seeded
    before = await db.scalar(select(func.count()).select_from(Invoice))

    await seed(db, reset=False)

    assert await db.scalar(select(func.count()).select_from(Invoice)) == before
    assert await db.scalar(select(func.count()).select_from(Supplier)) == len(SUPPLIERS)
    assert await db.scalar(select(func.count()).select_from(Category)) > 0
