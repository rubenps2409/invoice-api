"""Schemas de usuario.

Solo schemas: no hay router de usuarios todavía. El registro/login (con hash de
contraseña y JWT) se implementa en la semana 2. `UserRead` nunca expone el hash.
"""

from pydantic import BaseModel, ConfigDict, EmailStr, Field



class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=255)
    # bcrypt solo usa 72 bytes; se acota para evitar contraseñas gigantes (DoS).
    password: str = Field(min_length=8, max_length=128)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
