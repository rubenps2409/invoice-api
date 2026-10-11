from fastapi import FastAPI

from invoice_api.routers import categories

app = FastAPI(title="Invoice API")

app.include_router(categories.router)