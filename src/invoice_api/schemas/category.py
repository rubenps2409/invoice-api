from pydantic import BaseModel, ConfigDict, Field


class CategoryBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)


class CategoryCreate(CategoryBase):
    model_config = ConfigDict(extra="forbid")


class CategoryUpdate(CategoryBase):
    model_config = ConfigDict(extra="forbid")


class CategoryRead(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int