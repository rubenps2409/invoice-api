"""What the app releases when it shuts down."""

from pydantic import SecretStr

from invoice_api.config import settings
from invoice_api.main import app
from invoice_api.services import extraction


async def test_shutdown_closes_the_model_client(monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", SecretStr("sk-ant-test"))
    extraction._client.cache_clear()
    client = extraction._client()

    async with app.router.lifespan_context(app):
        assert not client.is_closed()

    assert client.is_closed()
    assert extraction._client.cache_info().currsize == 0


async def test_shutdown_without_a_model_client_is_fine():
    extraction._client.cache_clear()

    async with app.router.lifespan_context(app):
        pass

    assert extraction._client.cache_info().currsize == 0
