from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from invoice_api.dependencies import CurrentUserId, DbSession
from invoice_api.models import Category
from invoice_api.schemas.extraction import ExtractionRequest
from invoice_api.schemas.invoice import InvoiceRead
from invoice_api.services.extraction import (
    ExtractionError,
    ExtractionInvalidOutput,
    ExtractionTimeout,
    ExtractionUnavailable,
    InvoiceExtractor,
    get_extractor,
)
from invoice_api.services.invoice_creation import (
    DuplicateInvoiceError,
    create_invoice_from_extraction,
)
from invoice_api.services.llm_usage import record_attempts

router = APIRouter(prefix="/invoices", tags=["invoices"])

_ERROR_STATUS: dict[type[ExtractionError], int] = {
    ExtractionInvalidOutput: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ExtractionTimeout: status.HTTP_504_GATEWAY_TIMEOUT,
    ExtractionUnavailable: status.HTTP_502_BAD_GATEWAY,
}


@router.post(
    "/extract",
    response_model=InvoiceRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"description": "The invoice already exists for that supplier"},
        422: {"description": "Invalid text, or no valid invoice could be extracted"},
        502: {"description": "The model API failed"},
        503: {"description": "Extraction is not configured on this server"},
        504: {"description": "The model took too long to answer"},
    },
)
def extract_invoice(
    data: ExtractionRequest,
    db: DbSession,
    user_id: CurrentUserId,
    extractor: Annotated[InvoiceExtractor, Depends(get_extractor)],
):
    """Extract an invoice from raw text and store it as a pending invoice."""
    categories = db.scalars(
        select(Category.name).where(Category.user_id == user_id).order_by(Category.name)
    ).all()

    # The user lookup and the query above opened a transaction. End it so the
    # pooled connection is not held while the (slow) model call runs.
    db.rollback()

    try:
        result = extractor.extract(data.text, categories)
    except ExtractionError as exc:
        # The tokens were spent even though the extraction failed.
        record_attempts(db, user_id, exc.attempts, model=extractor.model)
        raise HTTPException(_ERROR_STATUS[type(exc)], str(exc)) from exc

    record_attempts(db, user_id, result.attempts, model=extractor.model)

    try:
        return create_invoice_from_extraction(db, user_id, result.invoice)
    except DuplicateInvoiceError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
