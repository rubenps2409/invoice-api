from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from psycopg.errors import NotNullViolation, UniqueViolation
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
        "currency": "EUR",
        "category_name": None,
    }
    return ExtractedInvoice.model_validate({**data, **overrides})


async def make_user(db, email) -> User:
    user = User(email=email, hashed_password="x")
    db.add(user)
    await db.commit()
    return user


@pytest.fixture
async def user(db):
    return await make_user(db, "a@example.com")


@pytest.fixture
async def other_user(db):
    return await make_user(db, "b@example.com")


async def count(db, model) -> int:
    return await db.scalar(select(func.count()).select_from(model)) or 0


# --- the stored invoice -----------------------------------------------------


async def test_stores_the_invoice_for_the_user(db, user):
    invoice = await create_invoice_from_extraction(db, user.id, extracted())

    stored = await db.get(Invoice, invoice.id)
    assert stored is not None
    assert stored.user_id == user.id
    assert stored.number == "INV-1"
    assert stored.issue_date == date(2026, 3, 15)
    assert stored.base_amount == Decimal("100.00")
    assert stored.tax_amount == Decimal("21.00")
    assert stored.total_amount == Decimal("121.00")
    assert stored.status == InvoiceStatus.PENDING


# --- supplier ---------------------------------------------------------------


async def test_creates_the_supplier_when_it_is_new(db, user):
    invoice = await create_invoice_from_extraction(db, user.id, extracted())

    supplier = await db.get(Supplier, invoice.supplier_id)
    assert supplier is not None
    assert (supplier.name, supplier.user_id) == ("Acme S.L.", user.id)


async def test_reuses_an_existing_supplier(db, user):
    first = await create_invoice_from_extraction(db, user.id, extracted())
    second = await create_invoice_from_extraction(
        db, user.id, extracted(invoice_number="INV-2")
    )

    assert second.supplier_id == first.supplier_id
    assert await count(db, Supplier) == 1


async def test_supplier_match_ignores_case(db, user):
    first = await create_invoice_from_extraction(db, user.id, extracted())
    second = await create_invoice_from_extraction(
        db, user.id, extracted(supplier_name="ACME S.L.", invoice_number="INV-2")
    )

    assert second.supplier_id == first.supplier_id
    assert await count(db, Supplier) == 1


async def test_does_not_reuse_another_users_supplier(db, user, other_user):
    mine = await create_invoice_from_extraction(db, user.id, extracted())
    theirs = await create_invoice_from_extraction(db, other_user.id, extracted())

    their_supplier = await db.get(Supplier, theirs.supplier_id)
    assert their_supplier is not None
    assert theirs.supplier_id != mine.supplier_id
    assert their_supplier.user_id == other_user.id


async def test_recovers_when_the_supplier_is_created_concurrently(db, user, monkeypatch):
    existing = Supplier(name="Acme S.L.", user_id=user.id)
    db.add(existing)
    await db.commit()
    real_find = invoice_creation._find_supplier
    calls = []

    async def find_after_a_lost_race(db_, user_id, name, tax_id):
        calls.append(name)
        # First lookup "misses" (the other request had not committed yet).
        return None if len(calls) == 1 else await real_find(db_, user_id, name, tax_id)

    monkeypatch.setattr(invoice_creation, "_find_supplier", find_after_a_lost_race)

    invoice = await create_invoice_from_extraction(db, user.id, extracted())

    assert invoice.supplier_id == existing.id
    assert await count(db, Supplier) == 1
    assert len(calls) == 2


# --- recognising the same supplier ------------------------------------------


async def add_supplier(db, user, name, tax_id=None) -> Supplier:
    supplier = Supplier(name=name, tax_id=tax_id, user_id=user.id)
    db.add(supplier)
    await db.commit()
    return supplier


@pytest.mark.parametrize("variant", ["ACME, S.L.", "Acme SL", "acme s.l.u.", "Acmé"])
async def test_a_spelling_variant_of_the_name_reuses_the_supplier(db, user, variant):
    first = await create_invoice_from_extraction(db, user.id, extracted())

    second = await create_invoice_from_extraction(
        db, user.id, extracted(supplier_name=variant, invoice_number="INV-2")
    )

    assert second.supplier_id == first.supplier_id
    assert await count(db, Supplier) == 1


async def test_a_name_variant_cannot_hide_a_duplicate_invoice(db, user):
    """The original bug: "ACME, S.L." used to create a second supplier, so the
    (user, supplier, number) uniqueness never saw the repeated invoice."""
    await create_invoice_from_extraction(db, user.id, extracted())

    with pytest.raises(DuplicateInvoiceError):
        await create_invoice_from_extraction(
            db, user.id, extracted(supplier_name="ACME, S.L.")
        )

    assert await count(db, Invoice) == 1
    assert await count(db, Supplier) == 1


async def test_the_tax_id_is_stored_normalised(db, user):
    invoice = await create_invoice_from_extraction(
        db, user.id, extracted(supplier_tax_id="ES-B12.345.678")
    )

    supplier = await db.get(Supplier, invoice.supplier_id)
    assert supplier is not None
    assert supplier.tax_id == "B12345678"


async def test_the_same_tax_id_reuses_the_supplier_even_if_the_name_differs(db, user):
    first = await create_invoice_from_extraction(
        db, user.id, extracted(supplier_tax_id="B12345678")
    )

    second = await create_invoice_from_extraction(
        db,
        user.id,
        extracted(
            supplier_name="Acme Soluciones Integrales",
            supplier_tax_id="b-12345678",
            invoice_number="INV-2",
        ),
    )

    assert second.supplier_id == first.supplier_id
    assert await count(db, Supplier) == 1


async def test_a_supplier_known_only_by_name_learns_its_tax_id(db, user):
    existing = await add_supplier(db, user, "Acme S.L.")

    invoice = await create_invoice_from_extraction(
        db, user.id, extracted(supplier_tax_id="B12345678")
    )

    assert invoice.supplier_id == existing.id
    assert existing.tax_id == "B12345678"
    assert await count(db, Supplier) == 1


async def test_an_invoice_without_tax_id_reuses_a_supplier_that_has_one(db, user):
    existing = await add_supplier(db, user, "Acme S.L.", tax_id="B12345678")

    invoice = await create_invoice_from_extraction(
        db, user.id, extracted(supplier_tax_id=None)
    )

    assert invoice.supplier_id == existing.id
    assert existing.tax_id == "B12345678"


async def test_the_same_name_with_a_different_tax_id_is_another_company(db, user):
    first = await add_supplier(db, user, "Acme S.L.", tax_id="B12345678")

    invoice = await create_invoice_from_extraction(
        db, user.id, extracted(supplier_name="ACME, S.L.", supplier_tax_id="A98765432")
    )

    assert invoice.supplier_id != first.id
    assert await count(db, Supplier) == 2


async def test_two_companies_with_exactly_the_same_name_can_both_be_stored(db, user):
    """Names are unique per user, so the second one gets its tax id appended."""
    first = await add_supplier(db, user, "Acme S.L.", tax_id="B12345678")

    invoice = await create_invoice_from_extraction(
        db, user.id, extracted(supplier_tax_id="A98765432")
    )

    second = await db.get(Supplier, invoice.supplier_id)
    assert second is not None
    assert second.id != first.id
    assert second.name == "Acme S.L. (A98765432)"
    assert second.tax_id == "A98765432"


async def test_a_very_long_name_still_fits_when_the_tax_id_is_appended(db, user):
    long_name = "A" * 255
    await add_supplier(db, user, long_name, tax_id="B12345678")

    invoice = await create_invoice_from_extraction(
        db, user.id, extracted(supplier_name=long_name, supplier_tax_id="A98765432")
    )

    second = await db.get(Supplier, invoice.supplier_id)
    assert second is not None
    assert len(second.name) == 255
    assert second.name.endswith(" (A98765432)")


async def test_the_same_tax_id_for_another_user_is_a_separate_supplier(db, user, other_user):
    mine = await create_invoice_from_extraction(
        db, user.id, extracted(supplier_tax_id="B12345678")
    )

    theirs = await create_invoice_from_extraction(
        db, other_user.id, extracted(supplier_tax_id="B12345678")
    )

    assert theirs.supplier_id != mine.supplier_id
    assert await count(db, Supplier) == 2


async def test_a_tax_id_lost_race_reuses_the_supplier_that_won(db, user, monkeypatch):
    """The supplier known by name is about to learn a tax id that a concurrent
    request already gave to another supplier."""
    by_name = await add_supplier(db, user, "Acme S.L.")
    winner = await add_supplier(db, user, "Acme Soluciones", tax_id="B12345678")
    real_find = invoice_creation._find_supplier
    calls = []

    async def stale_first_lookup(db_, user_id, name, tax_id):
        calls.append(tax_id)
        return by_name if len(calls) == 1 else await real_find(db_, user_id, name, tax_id)

    monkeypatch.setattr(invoice_creation, "_find_supplier", stale_first_lookup)

    invoice = await create_invoice_from_extraction(
        db, user.id, extracted(supplier_tax_id="B12345678")
    )

    assert invoice.supplier_id == winner.id
    assert by_name.tax_id is None


async def test_an_integrity_error_that_is_not_a_lost_race_is_not_swallowed(
    db, user, monkeypatch
):
    by_name = await add_supplier(db, user, "Acme S.L.")
    await add_supplier(db, user, "Other", tax_id="B12345678")
    # The lookup keeps answering with the same supplier, so there is no "winner"
    # to fall back on: the conflict must surface instead of being hidden.

    async def always_by_name(*args):
        await db.refresh(by_name)  # the failed savepoint expired it
        return by_name

    monkeypatch.setattr(invoice_creation, "_find_supplier", always_by_name)

    with pytest.raises(IntegrityError):
        await create_invoice_from_extraction(
            db, user.id, extracted(supplier_tax_id="B12345678")
        )


async def test_unrelated_integrity_errors_are_not_swallowed(db):
    with pytest.raises(IntegrityError):
        await create_invoice_from_extraction(db, 999_999, extracted())


# --- category ---------------------------------------------------------------


async def test_links_an_existing_category(db, user):
    category = Category(name="Software", user_id=user.id)
    db.add(category)
    await db.commit()

    invoice = await create_invoice_from_extraction(
        db, user.id, extracted(category_name="Software")
    )

    assert invoice.category_id == category.id


async def test_no_category_name_leaves_it_empty(db, user):
    invoice = await create_invoice_from_extraction(db, user.id, extracted())

    assert invoice.category_id is None


async def test_unknown_category_leaves_it_empty_and_creates_nothing(db, user):
    invoice = await create_invoice_from_extraction(
        db, user.id, extracted(category_name="Nonexistent")
    )

    assert invoice.category_id is None
    assert await count(db, Category) == 0


async def test_never_links_another_users_category(db, user, other_user):
    db.add(Category(name="Software", user_id=other_user.id))
    await db.commit()

    invoice = await create_invoice_from_extraction(
        db, user.id, extracted(category_name="Software")
    )

    assert invoice.category_id is None


# --- duplicates -------------------------------------------------------------


async def test_duplicate_number_for_the_same_supplier_raises(db, user):
    first_id = (await create_invoice_from_extraction(db, user.id, extracted())).id

    with pytest.raises(DuplicateInvoiceError):
        await create_invoice_from_extraction(db, user.id, extracted())

    assert await count(db, Invoice) == 1
    assert await count(db, Supplier) == 1
    assert await db.get(Invoice, first_id) is not None


async def test_same_number_for_another_supplier_is_fine(db, user):
    await create_invoice_from_extraction(db, user.id, extracted())

    other = await create_invoice_from_extraction(
        db, user.id, extracted(supplier_name="Globex")
    )

    assert other.number == "INV-1"
    assert await count(db, Invoice) == 2


async def test_same_number_and_supplier_for_another_user_is_fine(db, user, other_user):
    await create_invoice_from_extraction(db, user.id, extracted())

    await create_invoice_from_extraction(db, other_user.id, extracted())

    assert await count(db, Invoice) == 2


async def test_a_unique_violation_of_another_constraint_is_not_reported_as_a_duplicate(
    db, user, monkeypatch
):
    class OtherConstraint(UniqueViolation):
        diag = SimpleNamespace(constraint_name="uq_something_else")  # type: ignore[assignment]

    async def failing_commit():
        raise IntegrityError("INSERT ...", {}, OtherConstraint("dup"))

    monkeypatch.setattr(db, "commit", failing_commit)

    with pytest.raises(IntegrityError):
        await create_invoice_from_extraction(db, user.id, extracted())


async def test_other_commit_errors_are_not_reported_as_duplicates(db, user, monkeypatch):
    async def failing_commit():
        raise IntegrityError("INSERT ...", {}, NotNullViolation("null value"))

    monkeypatch.setattr(db, "commit", failing_commit)

    with pytest.raises(IntegrityError):
        await create_invoice_from_extraction(db, user.id, extracted())
