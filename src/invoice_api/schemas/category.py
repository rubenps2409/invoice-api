from pydantic import BaseModel, ConfigDict

from invoice_api.schemas.common import Str100


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Str100


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Str100


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
