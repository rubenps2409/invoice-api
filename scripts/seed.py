import argparse
import asyncio
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_api.config import Environment, settings
from invoice_api.database import SessionLocal, engine
from invoice_api.models import Category, Invoice, InvoiceStatus, Supplier, User
from invoice_api.security import hash_password_async, verify_password_async

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-password"

SEED = 2026
INVOICE_COUNT = 40
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


@dataclass(frozen=True)
class SeedSupplier:
    name: str
    category: str
    amount_range: tuple[int, int]  # taxable base, in the supplier's currency
    tax_id: str | None = None  # None: simplified invoices, or a foreign supplier
    vat_rate: int = 21  # in %
    withholding_rate: int = 0  # income-tax withholding (IRPF), in %; 0 = none
    currency: str = "EUR"
    number_prefix: str = "INV"


# All names, tax ids and figures are invented.
SUPPLIERS = [
    SeedSupplier(
        "Electra Norte Energía S.L.", "Utilities", (60, 240), "B83920154", number_prefix="EN"
    ),
    SeedSupplier(
        "Telefonía Costa Verde S.A.", "Utilities", (30, 120), "A27384950", number_prefix="TCV"
    ),
    SeedSupplier(
        "Nubesoft Cloud S.L.",
        "Software and licenses",
        (25, 480),
        "B76105432",
        number_prefix="NS",
    ),
    SeedSupplier(
        "Papelería El Cuaderno S.L.",
        "Office supplies",
        (15, 180),
        "B91827364",
        number_prefix="PC",
    ),
    SeedSupplier(
        "Estudio Brújula Publicidad", "Marketing", (300, 2400), "B64738291", number_prefix="EB"
    ),
    SeedSupplier(
        "Gestoría Almendral y Asociados",
        "Professional services",
        (150, 900),
        "B52849163",
        number_prefix="GA",
    ),
    SeedSupplier(
        "Viajes Horizonte Azul S.A.",
        "Travel and meals",
        (80, 1200),
        "A41526378",
        vat_rate=10,
        number_prefix="VH",
    ),
    # Simplified invoices carry no tax id.
    SeedSupplier(
        "Cafetería Los Olivos", "Travel and meals", (12, 95), vat_rate=10, number_prefix="CO"
    ),
    # Self-employed professionals: their invoices carry an IRPF withholding.
    SeedSupplier(
        "Lucía Ferrer Montoya",
        "Marketing",
        (200, 1800),
        "34567890T",
        withholding_rate=15,
        number_prefix="LF",
    ),
    SeedSupplier(
        "Raúl Cebrián Soto",
        "Professional services",
        (150, 900),
        "28374651M",
        withholding_rate=15,
        number_prefix="RC",
    ),
    # Foreign suppliers, invoicing in their own currency.
    SeedSupplier(
        "Cumulus Hosting Inc.",
        "Software and licenses",
        (20, 300),
        vat_rate=0,  # reverse charge
        currency="USD",
        number_prefix="CH",
    ),
    SeedSupplier(
        "Thames Print & Design Ltd",
        "Marketing",
        (150, 900),
        vat_rate=20,
        currency="GBP",
        number_prefix="TP",
    ),
]

# Recent invoices are mostly still pending; old ones are mostly settled.
RECENT_DAYS = 60
RECENT_STATUS_WEIGHTS = [
    (InvoiceStatus.PENDING, 60),
    (InvoiceStatus.PAID, 28),
    (InvoiceStatus.PARTIALLY_PAID, 7),
    (InvoiceStatus.CANCELLED, 5),
]
OLD_STATUS_WEIGHTS = [
    (InvoiceStatus.PAID, 80),
    (InvoiceStatus.PARTIALLY_PAID, 8),
    (InvoiceStatus.CANCELLED, 7),
    (InvoiceStatus.PENDING, 5),
]

DISCOUNT_PROBABILITY = 0.15
DISCOUNT_RATES = (5, 10, 15)  # in %
CREDIT_NOTE_PROBABILITY = 0.05
UNCATEGORIZED_PROBABILITY = 0.1

CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


async def ensure_demo_user(db: AsyncSession) -> User:
    user = await db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if user is None:
        user = User(email=DEMO_EMAIL, hashed_password=await hash_password_async(DEMO_PASSWORD))
        db.add(user)
    elif not await verify_password_async(DEMO_PASSWORD, user.hashed_password):
        user.hashed_password = await hash_password_async(DEMO_PASSWORD)
    await db.flush()
    return user


async def reset_demo_data(db: AsyncSession, user_id: int) -> None:
    for model in (Invoice, Supplier, Category):
        await db.execute(delete(model).where(model.user_id == user_id))
    await db.flush()


async def get_or_create_categories(db: AsyncSession, user_id: int) -> dict[str, Category]:
    rows = await db.scalars(select(Category).where(Category.user_id == user_id))
    existing = {c.name: c for c in rows}
    for name in CATEGORIES:
        if name not in existing:
            existing[name] = Category(name=name, user_id=user_id)
            db.add(existing[name])
    await db.flush()
    return existing


async def get_or_create_suppliers(db: AsyncSession, user_id: int) -> dict[str, Supplier]:
    rows = await db.scalars(select(Supplier).where(Supplier.user_id == user_id))
    existing = {s.name: s for s in rows}
    for seed_supplier in SUPPLIERS:
        supplier = existing.get(seed_supplier.name)
        if supplier is None:
            supplier = Supplier(
                name=seed_supplier.name, tax_id=seed_supplier.tax_id, user_id=user_id
            )
            db.add(supplier)
            existing[seed_supplier.name] = supplier
        elif supplier.tax_id is None:
            supplier.tax_id = seed_supplier.tax_id
    await db.flush()
    return existing


def pick_status(rng: random.Random, issue_date: date) -> InvoiceStatus:
    recent = (END_DATE - issue_date).days <= RECENT_DAYS
    statuses, weights = zip(
        *(RECENT_STATUS_WEIGHTS if recent else OLD_STATUS_WEIGHTS), strict=True
    )
    return rng.choices(statuses, weights)[0]


def build_invoices(
    suppliers: dict[str, Supplier],
    categories: dict[str, Category],
    user_id: int,
) -> list[Invoice]:
    rng = random.Random(SEED)
    span_days = (END_DATE - START_DATE).days
    counters: dict[str, int] = {}
    invoices: list[Invoice] = []

    for _ in range(INVOICE_COUNT):
        seed_supplier = rng.choice(SUPPLIERS)
        supplier = suppliers[seed_supplier.name]
        issue_date = START_DATE + timedelta(days=rng.randint(0, span_days))

        low, high = seed_supplier.amount_range
        base = money(Decimal(rng.randint(low * 100, high * 100)) / 100)
        if rng.random() < DISCOUNT_PROBABILITY:
            # An invoice's base is the taxable amount AFTER any discount.
            base = money(base * (100 - rng.choice(DISCOUNT_RATES)) / 100)
        tax = money(base * seed_supplier.vat_rate / 100)
        withholding = money(base * seed_supplier.withholding_rate / 100)

        # A credit note reverses every amount of an earlier invoice.
        credit_note = rng.random() < CREDIT_NOTE_PROBABILITY
        sign = -1 if credit_note else 1

        counters[seed_supplier.name] = counters.get(seed_supplier.name, 0) + 1
        kind = "R-" if credit_note else ""
        number = (
            f"{seed_supplier.number_prefix}-{kind}{issue_date.year}-"
            f"{counters[seed_supplier.name]:04d}"
        )

        # ~10% of invoices are left uncategorized.
        category = (
            None
            if rng.random() < UNCATEGORIZED_PROBABILITY
            else categories[seed_supplier.category]
        )

        invoices.append(
            Invoice(
                number=number,
                supplier_id=supplier.id,
                category_id=category.id if category else None,
                user_id=user_id,
                base_amount=sign * base,
                tax_amount=sign * tax,
                withholding_amount=sign * withholding,
                total_amount=sign * (base + tax - withholding),
                currency=seed_supplier.currency,
                issue_date=issue_date,
                status=pick_status(rng, issue_date),
            )
        )
    return invoices


async def seed(db: AsyncSession, *, reset: bool) -> None:
    user = await ensure_demo_user(db)
    if reset:
        await reset_demo_data(db, user.id)

    categories = await get_or_create_categories(db, user.id)
    suppliers = await get_or_create_suppliers(db, user.id)

    # Skip invoices that already exist so the script can be re-run safely.
    rows = await db.execute(
        select(Invoice.supplier_id, Invoice.number).where(Invoice.user_id == user.id)
    )
    existing = set(rows.all())
    new_invoices = [
        inv
        for inv in build_invoices(suppliers, categories, user.id)
        if (inv.supplier_id, inv.number) not in existing
    ]
    db.add_all(new_invoices)
    await db.commit()

    total = await db.scalar(
        select(func.count()).select_from(Invoice).where(Invoice.user_id == user.id)
    )
    print(
        f"OK: {len(new_invoices)} new invoices ({total} total), "
        f"{len(suppliers)} suppliers, {len(categories)} categories."
    )
    print(f"Demo login: {DEMO_EMAIL} / {DEMO_PASSWORD}")


async def _seed_and_close(*, reset: bool) -> None:
    try:
        async with SessionLocal() as db:
            await seed(db, reset=reset)
    finally:
        await engine.dispose()


def main() -> None:
    # Known name, known password: never create that account in a real deployment.
    if settings.ENVIRONMENT is Environment.PRODUCTION:
        raise SystemExit("Refusing to load demo data with ENVIRONMENT=production.")
    parser = argparse.ArgumentParser(description="Load synthetic sample data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete the demo user's suppliers, categories and invoices first",
    )
    args = parser.parse_args()

    # psycopg cannot run in async mode on Windows' default ProactorEventLoop.
    asyncio.run(_seed_and_close(reset=args.reset), loop_factory=asyncio.SelectorEventLoop)


if __name__ == "__main__":
    main()
