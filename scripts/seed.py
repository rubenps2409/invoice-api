import argparse
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from invoice_api.database import SessionLocal
from invoice_api.models import Category, Invoice, InvoiceStatus, Supplier, User
from invoice_api.security import hash_password, verify_password

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-password"

SEED = 2026
INVOICE_COUNT = 28
START_DATE = date(2026, 1, 5)
END_DATE = date(2026, 10, 9)

CATEGORIES = [
    "Utilities",
    "Software and licenses",
    "Office supplies",
    "Marketing",
    "Professional services",
    "Travel and meals",
]

# (name, category, (min_base, max_base), VAT rate in %)
SUPPLIERS = [
    ("Electra Norte Energía S.L.", "Utilities", (60, 240), 21),
    ("Nubesoft Cloud S.L.", "Software and licenses", (25, 480), 21),
    ("Papelería El Cuaderno S.L.", "Office supplies", (15, 180), 21),
    ("Estudio Brújula Publicidad", "Marketing", (300, 2400), 21),
    ("Gestoría Almendral y Asociados", "Professional services", (150, 900), 21),
    ("Viajes Horizonte Azul S.A.", "Travel and meals", (80, 1200), 10),
    ("Telefonía Costa Verde S.A.", "Utilities", (30, 120), 21),
    ("Cafetería Los Olivos", "Travel and meals", (12, 95), 10),
]

STATUS_WEIGHTS = [
    (InvoiceStatus.PAID, 60),
    (InvoiceStatus.PENDING, 25),
    (InvoiceStatus.PARTIALLY_PAID, 10),
    (InvoiceStatus.CANCELLED, 5),
]

CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def ensure_demo_user(db: Session) -> User:
    user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if user is None:
        user = User(email=DEMO_EMAIL, hashed_password=hash_password(DEMO_PASSWORD))
        db.add(user)
    elif not verify_password(DEMO_PASSWORD, user.hashed_password):
        user.hashed_password = hash_password(DEMO_PASSWORD)
    db.flush()
    return user


def reset_demo_data(db: Session, user_id: int) -> None:
    for model in (Invoice, Supplier, Category):
        db.execute(delete(model).where(model.user_id == user_id))
    db.flush()


def get_or_create_categories(db: Session, user_id: int) -> dict[str, Category]:
    existing = {
        c.name: c
        for c in db.scalars(select(Category).where(Category.user_id == user_id))
    }
    for name in CATEGORIES:
        if name not in existing:
            existing[name] = Category(name=name, user_id=user_id)
            db.add(existing[name])
    db.flush()
    return existing


def get_or_create_suppliers(db: Session, user_id: int) -> dict[str, Supplier]:
    existing = {
        s.name: s
        for s in db.scalars(select(Supplier).where(Supplier.user_id == user_id))
    }
    for name, *_ in SUPPLIERS:
        if name not in existing:
            existing[name] = Supplier(name=name, user_id=user_id)
            db.add(existing[name])
    db.flush()
    return existing


def build_invoices(
    suppliers: dict[str, Supplier],
    categories: dict[str, Category],
    user_id: int,
) -> list[Invoice]:
    rng = random.Random(SEED)
    span_days = (END_DATE - START_DATE).days
    statuses, weights = zip(*STATUS_WEIGHTS, strict=True)
    counters: dict[str, int] = {}
    invoices: list[Invoice] = []

    for _ in range(INVOICE_COUNT):
        name, category_name, (low, high), vat_rate = rng.choice(SUPPLIERS)
        supplier = suppliers[name]

        counters[name] = counters.get(name, 0) + 1
        issue_date = START_DATE + timedelta(days=rng.randint(0, span_days))

        base = money(Decimal(rng.randint(low * 100, high * 100)) / 100)
        tax = money(base * Decimal(vat_rate) / 100)

        # ~10% of invoices are left uncategorized.
        category = None if rng.random() < 0.1 else categories[category_name]

        invoices.append(
            Invoice(
                number=f"INV-{issue_date.year}-{counters[name]:04d}",
                supplier_id=supplier.id,
                category_id=category.id if category else None,
                user_id=user_id,
                base_amount=base,
                tax_amount=tax,
                total_amount=base + tax,
                issue_date=issue_date,
                status=rng.choices(statuses, weights)[0],
            )
        )
    return invoices


def seed(db: Session, *, reset: bool) -> None:
    user = ensure_demo_user(db)
    if reset:
        reset_demo_data(db, user.id)

    categories = get_or_create_categories(db, user.id)
    suppliers = get_or_create_suppliers(db, user.id)

    # Skip invoices that already exist so the script can be re-run safely.
    existing = set(
        db.execute(
            select(Invoice.supplier_id, Invoice.number).where(
                Invoice.user_id == user.id
            )
        ).all()
    )
    new_invoices = [
        inv
        for inv in build_invoices(suppliers, categories, user.id)
        if (inv.supplier_id, inv.number) not in existing
    ]
    db.add_all(new_invoices)
    db.commit()

    total = db.scalar(
        select(func.count()).select_from(Invoice).where(Invoice.user_id == user.id)
    )
    print(
        f"OK: {len(new_invoices)} new invoices ({total} total), "
        f"{len(suppliers)} suppliers, {len(categories)} categories."
    )
    print(f"Demo login: {DEMO_EMAIL} / {DEMO_PASSWORD}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load synthetic sample data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete the demo user's suppliers, categories and invoices first",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        seed(db, reset=args.reset)


if __name__ == "__main__":
    main()