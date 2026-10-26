from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from invoice_api.models.user import USER_EMAIL_MAX_LENGTH


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=USER_EMAIL_MAX_LENGTH)

    @field_validator("email")
    @classmethod
    def _lowercase_email(cls, value: str) -> str:
        return value.lower()

    password: str = Field(min_length=8, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
