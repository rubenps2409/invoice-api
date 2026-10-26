"""GET /api/health: public, checks that the database answers."""

from collections.abc import Generator
from unittest.mock import MagicMock

from sqlalchemy.exc import OperationalError

from invoice_api.database import get_db
from invoice_api.main import app

URL = "/api/health"


async def test_is_public_and_reports_ok(client):
    response = await client.get(URL)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_answers_503_when_the_database_is_down(client):
    broken = MagicMock()
    broken.execute.side_effect = OperationalError("SELECT 1", {}, Exception("down"))

    def broken_db() -> Generator[MagicMock]:
        yield broken

    app.dependency_overrides[get_db] = broken_db

    response = await client.get(URL)

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}


def test_every_route_is_registered_once():
    routes = [
        (route.path, tuple(sorted(route.methods)))
        for route in app.routes
        if hasattr(route, "methods")
    ]

    assert len(routes) == len(set(routes))
