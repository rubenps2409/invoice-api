from pydantic import BaseModel, ConfigDict

from invoice_api.schemas.common import Str255, TaxId


class SupplierCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Str255
    tax_id: TaxId | None = None


class SupplierUpdate(BaseModel):
    """PUT payload. `name` is required; `tax_id` is only changed when it is sent
    (an explicit null clears it), so renaming never erases a known tax id."""

    model_config = ConfigDict(extra="forbid")

    name: Str255
    tax_id: TaxId | None = None


class SupplierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    tax_id: str | None
