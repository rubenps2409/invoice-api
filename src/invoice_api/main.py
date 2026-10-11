from fastapi import FastAPI

from invoice_api.routers import categories, invoices, suppliers

app = FastAPI(title="Invoice API")

app.include_router(categories.router)
app.include_router(suppliers.router)
app.include_router(invoices.router)
