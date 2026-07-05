from app.templates_env import templates
import logging

from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import HTMLResponse

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.config import settings
from app.database import get_db
from app.i18n import get_translator
from app.models.user import User
from app.routers.deps import get_current_user_dep
from app.schemas.auth import NetworkCreate, LoginRequest, TokenResponse, PasswordResetRequest, PasswordResetConfirm
from app.services.auth_service import (
    authenticate_user, register_network, create_access_token, create_refresh_token,
    create_password_reset_token, verify_password_reset_token, hash_password,
    create_email_verification_token, verify_email_token,
)
from app.services.email_service import send_email


async def _send_verification_email(user: User) -> None:
    token = create_email_verification_token(user)
    verify_url = f"{settings.PUBLIC_URL}/auth/verify-email?token={token}"
    await send_email(
        user.email,
        "Подтвердите email — RestOS",
        f"<p>Чтобы подтвердить email, перейдите по ссылке:</p>"
        f"<p><a href='{verify_url}'>{verify_url}</a></p>",
    )

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)
from app.ratelimit import limiter

# Only mark cookies Secure once PUBLIC_URL is actually https — otherwise local/
# staging http deployments would silently stop sending the auth cookie at all.
_COOKIE_SECURE = settings.PUBLIC_URL.startswith("https://")



def _i18n_response(request: Request, template: str, extra: dict | None = None):
    gettext_fn, locale = get_translator(request)
    context = {"request": request, "_": gettext_fn, "locale": locale}
    if extra:
        context.update(extra)
    response = templates.TemplateResponse(template, context)
    if request.query_params.get("lang") in ("ru", "en"):
        response.set_cookie("lang", request.query_params["lang"], max_age=60 * 60 * 24 * 365)
    return response


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return _i18n_response(request, "login.html")


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return _i18n_response(request, "register.html")


@router.post("/register")
@limiter.limit("5/minute")
async def register(request: Request, data: NetworkCreate, response: Response, db: AsyncSession = Depends(get_db)):
    try:
        user = await register_network(data.name, data.slug, data.email, data.password, db)
    except Exception as e:
        logger.error("Registration error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))

    await _send_verification_email(user)

    access_token = create_access_token({"sub": str(user.id), "ver": 0})
    refresh_token = create_refresh_token({"sub": str(user.id), "ver": 0})

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
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select as _select
    from app.models.user import User as _User

    # Per-account lockout: 5 wrong passwords → 15 minutes. The per-IP rate
    # limit alone doesn't stop an attacker rotating IPs against one email.
    account = (await db.execute(_select(_User).where(_User.email == data.email))).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if account and account.locked_until and account.locked_until > now:
        raise HTTPException(status_code=429, detail="Слишком много попыток входа. Попробуйте через 15 минут.")

    user = await authenticate_user(data.email, data.password, db)
    if not user:
        if account:
            account.failed_logins = (account.failed_logins or 0) + 1
            if account.failed_logins >= 5:
                account.locked_until = now + timedelta(minutes=15)
                account.failed_logins = 0
                from app.services.audit import log_action
                log_action(db, account.network_id, account.email, "login_locked",
                           "5 неверных паролей подряд — вход заблокирован на 15 минут")
                logger.warning("Account %s locked after repeated failed logins", account.email)
            await db.commit()
        raise HTTPException(status_code=401, detail="Неверный email или пароль")

    if user.failed_logins or user.locked_until:
        user.failed_logins = 0
        user.locked_until = None
        await db.commit()

    ver = user.token_version or 0
    access_token = create_access_token({"sub": str(user.id), "ver": ver})
    refresh_token = create_refresh_token({"sub": str(user.id), "ver": ver})

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
    return _i18n_response(request, "forgot_password.html")


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
    return _i18n_response(request, "reset_password.html", {"token": token})


@router.post("/reset-password")
@limiter.limit("10/minute")
async def reset_password(request: Request, data: PasswordResetConfirm, db: AsyncSession = Depends(get_db)):
    user = await verify_password_reset_token(data.token, db)
    if not user:
        raise HTTPException(status_code=400, detail="Ссылка недействительна или устарела")
    user.hashed_password = hash_password(data.password)
    # Revoke every session on every device: anyone holding an old token
    # (a stolen phone, a fired employee's tablet) is logged out immediately.
    user.token_version = (user.token_version or 0) + 1
    user.failed_logins = 0
    user.locked_until = None
    await db.commit()
    logger.info("Password reset for user %s (all sessions revoked)", user.email)
    return {"message": "Пароль обновлён"}


@router.get("/verify-email", response_class=HTMLResponse)
async def verify_email(request: Request, token: str = "", db: AsyncSession = Depends(get_db)):
    user = await verify_email_token(token, db)
    if not user:
        return templates.TemplateResponse(
            "verify_email.html", {"request": request, "ok": False}, status_code=400
        )
    if not user.email_verified:
        user.email_verified = True
        await db.commit()
        logger.info("Email verified for user %s", user.email)
    return templates.TemplateResponse("verify_email.html", {"request": request, "ok": True})


@router.post("/resend-verification")
@limiter.limit("3/minute")
async def resend_verification(request: Request, current_user: User = Depends(get_current_user_dep)):
    if current_user.email_verified:
        return {"message": "Email уже подтверждён"}
    await _send_verification_email(current_user)
    return {"message": "Письмо отправлено"}
