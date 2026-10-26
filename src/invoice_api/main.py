from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request, status
from fastapi.responses import JSONResponse

from invoice_api.database import engine
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await close_client()
    await engine.dispose()


app = FastAPI(title="Invoice API", lifespan=lifespan)


@app.exception_handler(ExtractionNotConfigured)
async def extraction_not_configured(request: Request, exc: ExtractionNotConfigured):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Invoice extraction is not available"},
    )


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
