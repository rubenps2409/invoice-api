"""The logs: one line per request, JSON in production, nothing private in them."""

import json
import logging
import sys

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from invoice_api.config import Environment
from invoice_api.logging_config import JsonFormatter, configure_logging
from invoice_api.middleware import RequestLogMiddleware

LOGGER = "invoice_api.request"


async def ok(request):
    return PlainTextResponse("ok")


async def boom(request):
    raise RuntimeError("unexpected")


@pytest.fixture
async def http():
    app = Starlette(routes=[Route("/ok", ok), Route("/boom", boom), Route("/api/health", ok)])
    app.add_middleware(RequestLogMiddleware)
    transport = ASGITransport(app=app, raise_app_exceptions=False, client=("203.0.113.7", 1))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def request_records(caplog):
    return [r for r in caplog.records if r.name == LOGGER]


# --- the request log --------------------------------------------------------------


async def test_a_request_is_logged_with_method_path_status_and_duration(http, caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        await http.get("/ok")

    (record,) = request_records(caplog)
    assert (record.method, record.path, record.status) == ("GET", "/ok", 200)
    assert record.duration_ms >= 0
    assert record.getMessage().startswith("GET /ok 200 ")


async def test_a_failing_request_is_logged_as_500(http, caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        response = await http.get("/boom")

    (record,) = request_records(caplog)
    assert response.status_code == 500
    assert record.status == 500


async def test_nothing_private_reaches_the_log(http, caplog):
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await http.post(
            "/ok?email=ana@example.com",
            content="invoice text B12345678",
            headers={"Authorization": "Bearer secret-token"},
        )

    logged = " ".join(f"{r.getMessage()} {r.__dict__}" for r in request_records(caplog))
    for private in ("ana@example.com", "B12345678", "secret-token", "203.0.113.7"):
        assert private not in logged


async def test_the_health_check_is_only_logged_when_debugging(http, caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER):
        await http.get("/api/health")
    assert request_records(caplog) == []

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await http.get("/api/health")
    assert len(request_records(caplog)) == 1


# --- the format -------------------------------------------------------------------


@pytest.fixture
def restore_logging():
    names = ("", "uvicorn", "uvicorn.error", "uvicorn.access")
    saved = {
        name: (
            logging.getLogger(name).handlers[:],
            logging.getLogger(name).level,
            logging.getLogger(name).propagate,
        )
        for name in names
    }
    yield
    for name, (handlers, level, propagate) in saved.items():
        logger = logging.getLogger(name)
        logger.handlers[:] = handlers
        logger.setLevel(level)
        logger.propagate = propagate


def record(**extra) -> logging.LogRecord:
    made = logging.LogRecord(
        "invoice_api.x", logging.INFO, __file__, 1, "hello %s", ("you",), None
    )
    made.__dict__.update(extra)
    return made


def test_the_json_format_has_the_message_and_the_request_fields():
    line = JsonFormatter().format(
        record(method="GET", path="/ok", status=200, duration_ms=1.5)
    )

    data = json.loads(line)
    assert data["message"] == "hello you"
    assert data["level"] == "INFO"
    assert data["logger"] == "invoice_api.x"
    assert (data["method"], data["path"], data["status"], data["duration_ms"]) == (
        "GET",
        "/ok",
        200,
        1.5,
    )


def test_the_json_format_includes_the_traceback_of_an_error():
    try:
        raise ValueError("bad")
    except ValueError:
        made = record()
        made.exc_info = sys.exc_info()

    assert "ValueError: bad" in json.loads(JsonFormatter().format(made))["exception"]


def test_production_logs_json_and_development_logs_text(restore_logging):
    configure_logging(Environment.PRODUCTION, "INFO")
    assert isinstance(logging.getLogger().handlers[0].formatter, JsonFormatter)

    configure_logging(Environment.DEVELOPMENT, "INFO")
    assert not isinstance(logging.getLogger().handlers[0].formatter, JsonFormatter)


def test_uvicorns_access_log_is_replaced_by_the_request_log(restore_logging):
    configure_logging(Environment.DEVELOPMENT, "INFO")

    access = logging.getLogger("uvicorn.access")
    assert access.handlers == [] and not access.propagate
    assert logging.getLogger("uvicorn.error").propagate


def test_the_level_comes_from_the_setting(restore_logging):
    configure_logging(Environment.DEVELOPMENT, "WARNING")

    assert logging.getLogger().level == logging.WARNING
