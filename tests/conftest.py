from collections.abc import Callable, Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from invoice_api.config import settings
from invoice_api.database import get_db
from invoice_api.main import app
from invoice_api.models import Base

TEST_DB_NAME = "invoice_test"


@pytest.fixture(scope="session")
def engine() -> Generator[Engine]:
    url = make_url(settings.DATABASE_URL).set(database=TEST_DB_NAME)
    # Safety guard: never run destructive setup against a non-test database.
    assert url.database == TEST_DB_NAME

    test_engine = create_engine(url)
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def db(engine: Engine) -> Generator[Session]:
    connection = engine.connect()
    outer_transaction = connection.begin()
    # commit()/rollback() inside the app only affect a SAVEPOINT of the
    # outer transaction, which is rolled back when the test ends.
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture
def client(db: Session) -> Generator[TestClient]:
    def override_get_db() -> Generator[Session]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


PASSWORD = "test-password-123"


def create_user(client: TestClient, email: str, password: str = PASSWORD) -> dict:
    response = client.post(
        "/api/auth/register", json={"email": email, "password": password}
    )
    assert response.status_code == 201, response.text
    return response.json()


def login_headers(
    client: TestClient, email: str, password: str = PASSWORD
) -> dict[str, str]:
    # The login endpoint takes form data (OAuth2 spec), hence data= and not json=.
    response = client.post(
        "/api/auth/login", data={"username": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def headers_a(client: TestClient) -> dict[str, str]:
    create_user(client, "a@example.com")
    return login_headers(client, "a@example.com")


@pytest.fixture
def headers_b(client: TestClient) -> dict[str, str]:
    create_user(client, "b@example.com")
    return login_headers(client, "b@example.com")


@pytest.fixture
def make_category(client: TestClient) -> Callable[..., dict]:
    def _make(headers: dict[str, str], name: str = "Utilities") -> dict:
        response = client.post("/api/categories", json={"name": name}, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture
def make_supplier(client: TestClient) -> Callable[..., dict]:
    def _make(headers: dict[str, str], name: str = "Acme S.L.") -> dict:
        response = client.post("/api/suppliers", json={"name": name}, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture
def make_invoice(client: TestClient) -> Callable[..., dict]:
    def _make(headers: dict[str, str], supplier_id: int, **overrides: Any) -> dict:
        payload = {
            "number": "INV-2026-0001",
            "supplier_id": supplier_id,
            "base_amount": "100.00",
            "tax_amount": "21.00",
            "total_amount": "121.00",
            "issue_date": "2026-03-15",
        }
        payload.update(overrides)
        response = client.post("/api/invoices", json=payload, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    return _make
