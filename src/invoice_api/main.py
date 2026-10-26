from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from invoice_api.config import Environment, settings
from invoice_api.database import engine
from invoice_api.logging_config import configure_logging
from invoice_api.middleware import RequestLogMiddleware
from invoice_api.routers import (
    auth,
    categories,
    extraction,
    health,
    invoices,
    suppliers,
    usage,
    users,
)
from invoice_api.services.extraction import ExtractionNotConfigured, close_client

# The web page lives inside the package, so it is installed with it.
_STATIC_DIR = Path(__file__).parent / "static"
_PAGE_HEADERS = {
    "Cache-Control": "no-cache",  # revalidate (ETag) so a deploy is seen at once
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


class _StaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers.update(_PAGE_HEADERS)
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await close_client()
    await engine.dispose()


async def extraction_not_configured(request: Request, exc: ExtractionNotConfigured):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Invoice extraction is not available"},
    )


def create_app(environment: Environment, enable_docs: bool | None = None) -> FastAPI:
    # The interactive docs list every route and field. Unless forced either way,
    # they are for development only.
    if enable_docs is None:
        enable_docs = environment is not Environment.PRODUCTION
    docs = {} if enable_docs else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(title="Invoice API", lifespan=lifespan, **docs)
    app.add_middleware(RequestLogMiddleware)
    app.add_exception_handler(ExtractionNotConfigured, extraction_not_configured)

    api_router = APIRouter(prefix="/api")
    api_router.include_router(categories.router)
    api_router.include_router(suppliers.router)
    api_router.include_router(extraction.router)
    api_router.include_router(invoices.router)
    api_router.include_router(auth.router)
    api_router.include_router(users.router)
    api_router.include_router(usage.router)
    api_router.include_router(health.router)
    app.include_router(api_router)

    # Only these two routes are added, so an unknown /api path still answers with the
    # API's own JSON 404 (a catch-all mount at / would shadow it).
    @app.get("/", include_in_schema=False)
    async def home() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html", headers=_PAGE_HEADERS)

    app.mount("/static", _StaticFiles(directory=_STATIC_DIR), name="static")
    return app


configure_logging(settings.ENVIRONMENT, settings.LOG_LEVEL)
app = create_app(settings.ENVIRONMENT, settings.ENABLE_DOCS)
