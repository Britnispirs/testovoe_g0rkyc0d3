from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict


class UserBase(BaseModel):
    email: str = Field(..., description="Email адрес пользователя")


class UserRegister(UserBase):
    password: str = Field(..., min_length=6, description="Пароль минимум 6 символов")


class UserLogin(UserBase):
    password: str = Field(..., description="Пароль")


class UserItem(UserBase):
    id: int
    is_active: bool = True
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserItem


class ForgotPasswordRequest(UserBase):
    pass


class ResetPasswordRequest(UserBase):
    code: str = Field(..., description="Одноразовый код сброса")
    new_password: str = Field(..., min_length=6, description="Новый пароль")
