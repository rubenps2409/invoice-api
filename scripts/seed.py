import argparse
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
 
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session
 
from invoice_api.database import SessionLocal
from invoice_api.models import Category, Invoice, InvoiceStatus, Supplier, User
 
DEMO_USER_ID = 1
DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD_PLACEHOLDER = "!seed-user-no-login"
 
SEED = 2026 
INVOICE_COUNT = 28
START_DATE = date(2026, 1, 5)
END_DATE = date(2026, 10, 9)
 
CATEGORIES = [
    "Suministros",
    "Software y licencias",
    "Material de oficina",
    "Marketing",
    "Servicios profesionales",
    "Viajes y dietas",
]
 

SUPPLIERS = [
    ("Electra Norte Energía S.L.", "Suministros", (60, 240), 21),
    ("Nubesoft Cloud S.L.", "Software y licencias", (25, 480), 21),
    ("Papelería El Cuaderno S.L.", "Material de oficina", (15, 180), 21),
    ("Estudio Brújula Publicidad", "Marketing", (300, 2400), 21),
    ("Gestoría Almendral y Asociados", "Servicios profesionales", (150, 900), 21),
    ("Viajes Horizonte Azul S.A.", "Viajes y dietas", (80, 1200), 10),
    ("Telefonía Costa Verde S.A.", "Suministros", (30, 120), 21),
    ("Cafetería Los Olivos", "Viajes y dietas", (12, 95), 10),
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
 
 
def ensure_demo_user(db: Session) -> None:
    if db.get(User, DEMO_USER_ID) is not None:
        return
    db.add(
        User(
            id=DEMO_USER_ID,
            email=DEMO_EMAIL,
            hashed_password=DEMO_PASSWORD_PLACEHOLDER,
        )
    )
    db.flush()
    
    db.execute(
        text(
            "SELECT setval(pg_get_serial_sequence('users', 'id'), "
            "(SELECT MAX(id) FROM users))"
        )
    )
 
 
def reset_demo_data(db: Session) -> None:
    
    for model in (Invoice, Supplier, Category):
        db.execute(delete(model).where(model.user_id == DEMO_USER_ID))
    db.flush()
 
 
def get_or_create_categories(db: Session) -> dict[str, Category]:
    existing = {
        c.name: c
        for c in db.scalars(select(Category).where(Category.user_id == DEMO_USER_ID))
    }
    for name in CATEGORIES:
        if name not in existing:
            existing[name] = Category(name=name, user_id=DEMO_USER_ID)
            db.add(existing[name])
    db.flush()
    return existing
 
 
def get_or_create_suppliers(db: Session) -> dict[str, Supplier]:
    existing = {
        s.name: s
        for s in db.scalars(select(Supplier).where(Supplier.user_id == DEMO_USER_ID))
    }
    for name, *_ in SUPPLIERS:
        if name not in existing:
            existing[name] = Supplier(name=name, user_id=DEMO_USER_ID)
            db.add(existing[name])
    db.flush()
    return existing
 
 
def build_invoices(
    suppliers: dict[str, Supplier], categories: dict[str, Category]
) -> list[Invoice]:
    rng = random.Random(SEED)
    span_days = (END_DATE - START_DATE).days
    statuses, weights = zip(*STATUS_WEIGHTS)
    counters: dict[str, int] = {}
    invoices: list[Invoice] = []
 
    for _ in range(INVOICE_COUNT):
        name, category_name, (low, high), vat_rate = rng.choice(SUPPLIERS)
        supplier = suppliers[name]
 
        counters[name] = counters.get(name, 0) + 1
        issue_date = START_DATE + timedelta(days=rng.randint(0, span_days))
 
        base = money(Decimal(rng.randint(low * 100, high * 100)) / 100)
        tax = money(base * Decimal(vat_rate) / 100)
 
        
        category = None if rng.random() < 0.1 else categories[category_name]
 
        invoices.append(
            Invoice(
                number=f"F-{issue_date.year}-{counters[name]:04d}",
                supplier_id=supplier.id,
                category_id=category.id if category else None,
                user_id=DEMO_USER_ID,
                base_amount=base,
                tax_amount=tax,
                total_amount=base + tax,
                issue_date=issue_date,
                status=rng.choices(statuses, weights)[0],
            )
        )
    return invoices
 
 
def seed(db: Session, *, reset: bool) -> None:
    ensure_demo_user(db)
    if reset:
        reset_demo_data(db)
 
    categories = get_or_create_categories(db)
    suppliers = get_or_create_suppliers(db)
 
    
    existing = set(
        db.execute(
            select(Invoice.supplier_id, Invoice.number).where(
                Invoice.user_id == DEMO_USER_ID
            )
        ).all()
    )
    new_invoices = [
        inv
        for inv in build_invoices(suppliers, categories)
        if (inv.supplier_id, inv.number) not in existing
    ]
    db.add_all(new_invoices)
    db.commit()
 
    total = db.scalar(
        select(func.count()).select_from(Invoice).where(Invoice.user_id == DEMO_USER_ID)
    )
    print(
        f"OK: {len(new_invoices)} facturas nuevas "
        f"({total} en total), {len(suppliers)} proveedores, {len(categories)} categorías."
    )
 
 
def main() -> None:
    parser = argparse.ArgumentParser(description="Carga datos sintéticos de ejemplo.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="borra antes los proveedores, categorías y facturas del usuario demo",
    )
    args = parser.parse_args()
 
    with SessionLocal() as db:
        seed(db, reset=args.reset)
 
 
if __name__ == "__main__":
    main()