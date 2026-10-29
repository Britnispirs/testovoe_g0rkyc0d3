import re
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Depends, status

from backend.app.models.user import (
    UserRegister,
    UserLogin,
    UserItem,
    TokenResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)
from backend.app.database import (
    db_create_user,
    db_get_user_by_email,
    db_set_reset_code,
    db_reset_password,
    db_seed_starter_events_for_user,
)
from backend.app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user_required,
)
from backend.app.services.email_service import (
    send_welcome_email,
    send_password_reset_code,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register_endpoint(payload: UserRegister):
    email = payload.email.strip().lower()
    if not EMAIL_REGEX.match(email):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Некорректный формат адреса электронной почты",
        )

    if len(payload.password) < 6:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Пароль должен содержать минимум 6 символов",
        )

    existing = db_get_user_by_email(email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь с таким email уже зарегистрирован",
        )

    pwd_hash, salt = hash_password(payload.password)
    user = db_create_user(email=email, password_hash=pwd_hash, salt=salt)

    # Seed starter events for the new user so they have initial schedule
    try:
        db_seed_starter_events_for_user(user.id)
    except Exception:
        pass

    # Send welcome email (via SMTP or console emulation)
    send_welcome_email(user.email)

    access_token = create_access_token(data={"sub": str(user.id), "email": user.email})
    return TokenResponse(access_token=access_token, user=user)


@router.post("/login", response_model=TokenResponse)
def login_endpoint(payload: UserLogin):
    email = payload.email.strip().lower()
    user_row = db_get_user_by_email(email)

    if not user_row or not user_row.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(payload.password, user_row["hashed_password"], user_row["salt"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = UserItem(
        id=user_row["id"],
        email=user_row["email"],
        is_active=bool(user_row["is_active"]),
        created_at=user_row["created_at"],
    )

    access_token = create_access_token(data={"sub": str(user.id), "email": user.email})
    return TokenResponse(access_token=access_token, user=user)


@router.get("/me", response_model=UserItem)
def get_current_user_profile(current_user: UserItem = Depends(get_current_user_required)):
    return current_user


@router.post("/forgot-password")
def forgot_password_endpoint(payload: ForgotPasswordRequest):
    email = payload.email.strip().lower()
    user_row = db_get_user_by_email(email)

    # Always return success message for privacy/security reasons
    if user_row:
        code = f"{secrets.randbelow(900000) + 100000}"
        expires_at = (datetime.now() + timedelta(minutes=15)).isoformat()
        db_set_reset_code(email, code, expires_at)
        send_password_reset_code(email, code)

    return {
        "status": "ok",
        "message": "Если данный email зарегистрирован, на него отправлен проверочный код.",
    }


@router.post("/reset-password")
def reset_password_endpoint(payload: ResetPasswordRequest):
    email = payload.email.strip().lower()
    if len(payload.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Новый пароль должен содержать минимум 6 символов",
        )

    new_hash, new_salt = hash_password(payload.new_password)
    success = db_reset_password(email, payload.code.strip(), new_hash, new_salt)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неверный или просроченный проверочный код",
        )

    return {"status": "ok", "message": "Пароль успешно изменен. Теперь вы можете войти."}

