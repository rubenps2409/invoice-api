from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from invoice_api.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

def get_db() -> Generator[Session, None, None]:
    with SessionLocal() as db:
        yield db