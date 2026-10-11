from pydantic import BaseModel, ConfigDict

from invoice_api.schemas.common import Str255


class SupplierCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Str255


class SupplierUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Str255


class SupplierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
