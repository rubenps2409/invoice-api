from fastapi import APIRouter, FastAPI

from invoice_api.routers import auth, categories, invoices, suppliers, users

app = FastAPI(title="Invoice API")

api_router = APIRouter(prefix="/api")
api_router.include_router(categories.router)
api_router.include_router(suppliers.router)
api_router.include_router(invoices.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)

app.include_router(api_router)
