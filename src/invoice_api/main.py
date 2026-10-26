from fastapi import APIRouter, FastAPI, Request, status
from fastapi.responses import JSONResponse

from invoice_api.routers import (
    auth,
    categories,
    extraction,
    invoices,
    suppliers,
    usage,
    users,
)
from invoice_api.services.extraction import ExtractionNotConfigured

app = FastAPI(title="Invoice API")


@app.exception_handler(ExtractionNotConfigured)
def extraction_not_configured(request: Request, exc: ExtractionNotConfigured):
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

app.include_router(api_router)
