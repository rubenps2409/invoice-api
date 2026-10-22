from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from invoice_api.models import Category, Invoice, InvoiceStatus, Supplier, User
from invoice_api.schemas.extraction import ExtractedInvoice
from invoice_api.services import invoice_creation
from invoice_api.services.invoice_creation import (
    DuplicateInvoiceError,
    create_invoice_from_extraction,
)


def extracted(**overrides) -> ExtractedInvoice:
    data = {
        "supplier_name": "Acme S.L.",
        "invoice_number": "INV-1",
        "issue_date": "2026-03-15",
        "base_amount": "100.00",
        "tax_amount": "21.00",
        "total_amount": "121.00",
        "category_name": None,
    }
    return ExtractedInvoice.model_validate({**data, **overrides})


def make_user(db, email) -> User:
    user = User(email=email, hashed_password="x")
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def user(db):
    return make_user(db, "a@example.com")


@pytest.fixture
def other_user(db):
    return make_user(db, "b@example.com")


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


# --- the stored invoice -----------------------------------------------------


def test_stores_the_invoice_for_the_user(db, user):
    invoice = create_invoice_from_extraction(db, user.id, extracted())

    stored = db.get(Invoice, invoice.id)
    assert stored is not None
    assert stored.user_id == user.id
    assert stored.number == "INV-1"
    assert stored.issue_date == date(2026, 3, 15)
    assert stored.base_amount == Decimal("100.00")
    assert stored.tax_amount == Decimal("21.00")
    assert stored.total_amount == Decimal("121.00")
    assert stored.status == InvoiceStatus.PENDING


# --- supplier ---------------------------------------------------------------


def test_creates_the_supplier_when_it_is_new(db, user):
    invoice = create_invoice_from_extraction(db, user.id, extracted())

    supplier = db.get(Supplier, invoice.supplier_id)
    assert supplier is not None
    assert (supplier.name, supplier.user_id) == ("Acme S.L.", user.id)


def test_reuses_an_existing_supplier(db, user):
    first = create_invoice_from_extraction(db, user.id, extracted())
    second = create_invoice_from_extraction(
        db, user.id, extracted(invoice_number="INV-2")
    )

    assert second.supplier_id == first.supplier_id
    assert count(db, Supplier) == 1


def test_supplier_match_ignores_case(db, user):
    first = create_invoice_from_extraction(db, user.id, extracted())
    second = create_invoice_from_extraction(
        db, user.id, extracted(supplier_name="ACME S.L.", invoice_number="INV-2")
    )

    assert second.supplier_id == first.supplier_id
    assert count(db, Supplier) == 1


def test_does_not_reuse_another_users_supplier(db, user, other_user):
    mine = create_invoice_from_extraction(db, user.id, extracted())
    theirs = create_invoice_from_extraction(db, other_user.id, extracted())

    their_supplier = db.get(Supplier, theirs.supplier_id)
    assert their_supplier is not None
    assert theirs.supplier_id != mine.supplier_id
    assert their_supplier.user_id == other_user.id


def test_recovers_when_the_supplier_is_created_concurrently(db, user, monkeypatch):
    existing = Supplier(name="Acme S.L.", user_id=user.id)
    db.add(existing)
    db.commit()
    real_find = invoice_creation._find_supplier
    calls = []

    def find_after_a_lost_race(db_, user_id, name):
        calls.append(name)
        # First lookup "misses" (the other request had not committed yet).
        return None if len(calls) == 1 else real_find(db_, user_id, name)

    monkeypatch.setattr(invoice_creation, "_find_supplier", find_after_a_lost_race)

    invoice = create_invoice_from_extraction(db, user.id, extracted())

    assert invoice.supplier_id == existing.id
    assert count(db, Supplier) == 1
    assert len(calls) == 2


def test_unrelated_integrity_errors_are_not_swallowed(db):
    with pytest.raises(IntegrityError):
        create_invoice_from_extraction(db, 999_999, extracted())


# --- category ---------------------------------------------------------------


def test_links_an_existing_category(db, user):
    category = Category(name="Software", user_id=user.id)
    db.add(category)
    db.commit()

    invoice = create_invoice_from_extraction(
        db, user.id, extracted(category_name="Software")
    )

    assert invoice.category_id == category.id


def test_no_category_name_leaves_it_empty(db, user):
    invoice = create_invoice_from_extraction(db, user.id, extracted())

    assert invoice.category_id is None


def test_unknown_category_leaves_it_empty_and_creates_nothing(db, user):
    invoice = create_invoice_from_extraction(
        db, user.id, extracted(category_name="Nonexistent")
    )

    assert invoice.category_id is None
    assert count(db, Category) == 0


def test_never_links_another_users_category(db, user, other_user):
    db.add(Category(name="Software", user_id=other_user.id))
    db.commit()

    invoice = create_invoice_from_extraction(
        db, user.id, extracted(category_name="Software")
    )

    assert invoice.category_id is None


# --- duplicates -------------------------------------------------------------


def test_duplicate_number_for_the_same_supplier_raises(db, user):
    first = create_invoice_from_extraction(db, user.id, extracted())

    with pytest.raises(DuplicateInvoiceError):
        create_invoice_from_extraction(db, user.id, extracted())

    assert count(db, Invoice) == 1
    assert count(db, Supplier) == 1
    assert db.get(Invoice, first.id) is not None


def test_same_number_for_another_supplier_is_fine(db, user):
    create_invoice_from_extraction(db, user.id, extracted())

    other = create_invoice_from_extraction(
        db, user.id, extracted(supplier_name="Globex")
    )

    assert other.number == "INV-1"
    assert count(db, Invoice) == 2


def test_same_number_and_supplier_for_another_user_is_fine(db, user, other_user):
    create_invoice_from_extraction(db, user.id, extracted())

    create_invoice_from_extraction(db, other_user.id, extracted())

    assert count(db, Invoice) == 2
