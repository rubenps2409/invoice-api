"""ENVIRONMENT=production: no public API docs, no demo data."""

import pytest
from httpx import ASGITransport, AsyncClient

from invoice_api.config import Environment, settings
from invoice_api.main import create_app
from scripts.seed import main as seed_main

DOCS_URLS = ["/docs", "/redoc", "/openapi.json"]


def client_of(environment: Environment, enable_docs: bool | None = None) -> AsyncClient:
    app = create_app(environment, enable_docs)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.parametrize("url", DOCS_URLS)
async def test_the_docs_are_served_in_development(url):
    async with client_of(Environment.DEVELOPMENT) as client:
        assert (await client.get(url)).status_code == 200


@pytest.mark.parametrize("url", DOCS_URLS)
async def test_the_docs_are_hidden_in_production(url):
    async with client_of(Environment.PRODUCTION) as client:
        assert (await client.get(url)).status_code == 404


@pytest.mark.parametrize("url", DOCS_URLS)
async def test_the_docs_can_be_forced_on_in_production(url):
    async with client_of(Environment.PRODUCTION, enable_docs=True) as client:
        assert (await client.get(url)).status_code == 200


@pytest.mark.parametrize("url", DOCS_URLS)
async def test_the_docs_can_be_forced_off_in_development(url):
    async with client_of(Environment.DEVELOPMENT, enable_docs=False) as client:
        assert (await client.get(url)).status_code == 404


def test_the_docs_setting_is_unset_by_default():
    assert type(settings).model_fields["ENABLE_DOCS"].default is None


async def test_the_api_itself_still_works_in_production():
    async with client_of(Environment.PRODUCTION) as client:
        # Reaches the router (and its authentication), so it is not a 404.
        assert (await client.get("/api/users/me")).status_code == 401


def test_development_is_the_default_environment():
    assert Environment.DEVELOPMENT is type(settings).model_fields["ENVIRONMENT"].default


def test_the_seed_refuses_to_run_in_production(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", Environment.PRODUCTION)

    with pytest.raises(SystemExit, match="production"):
        seed_main()
