from app.templates_env import templates
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.auth import NetworkCreate, LoginRequest, TokenResponse, PasswordResetRequest, PasswordResetConfirm
from app.services.auth_service import (
    authenticate_user, register_network, create_access_token, create_refresh_token,
    create_password_reset_token, verify_password_reset_token, hash_password,
)
from app.services.email_service import send_email

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address, enabled=settings.RATE_LIMIT_ENABLED)

# Only mark cookies Secure once PUBLIC_URL is actually https — otherwise local/
# staging http deployments would silently stop sending the auth cookie at all.
_COOKIE_SECURE = settings.PUBLIC_URL.startswith("https://")



@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@router.post("/register")
@limiter.limit("5/minute")
async def register(request: Request, data: NetworkCreate, response: Response, db: AsyncSession = Depends(get_db)):
    try:
        user = await register_network(data.name, data.slug, data.email, data.password, db)
    except Exception as e:
        logger.error("Registration error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))

    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="lax",
        secure=_COOKIE_SECURE,
        max_age=60 * 60 * 24 * 30,
    )
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=_COOKIE_SECURE,
        max_age=60 * settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    return TokenResponse(access_token=access_token)


@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, data: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(data.email, data.password, db)
    if not user:
        raise HTTPException(status_code=401, detail="Неверный email или пароль")

    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="lax",
        secure=_COOKIE_SECURE,
        max_age=60 * 60 * 24 * 30,
    )
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=_COOKIE_SECURE,
        max_age=60 * settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    return TokenResponse(access_token=access_token)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("refresh_token")
    response.delete_cookie("access_token")
    return {"message": "Выход выполнен"}


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse("forgot_password.html", {"request": request})


@router.post("/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(request: Request, data: PasswordResetRequest, db: AsyncSession = Depends(get_db)):
    # Always return 200 regardless of whether the email exists — a
    # differing response would let an attacker enumerate registered emails.
    user = (await db.execute(select(User).where(User.email == data.email))).scalar_one_or_none()
    if user:
        token = create_password_reset_token(user)
        reset_url = f"{settings.PUBLIC_URL}/auth/reset-password?token={token}"
        await send_email(
            user.email,
            "Восстановление пароля — RestOS",
            f"<p>Чтобы сбросить пароль, перейдите по ссылке (действует 30 минут):</p>"
            f"<p><a href='{reset_url}'>{reset_url}</a></p>"
            f"<p>Если вы не запрашивали сброс пароля, просто проигнорируйте это письмо.</p>",
        )
    return {"message": "Если email зарегистрирован, ссылка для сброса отправлена"}


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str = ""):
    return templates.TemplateResponse("reset_password.html", {"request": request, "token": token})


@router.post("/reset-password")
@limiter.limit("10/minute")
async def reset_password(request: Request, data: PasswordResetConfirm, db: AsyncSession = Depends(get_db)):
    user = await verify_password_reset_token(data.token, db)
    if not user:
        raise HTTPException(status_code=400, detail="Ссылка недействительна или устарела")
    user.hashed_password = hash_password(data.password)
    await db.commit()
    logger.info("Password reset for user %s", user.email)
    return {"message": "Пароль обновлён"}
