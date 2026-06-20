import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.auth import NetworkCreate, LoginRequest, TokenResponse
from app.services.auth_service import (
    authenticate_user, register_network, create_access_token, create_refresh_token
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/register")
async def register(data: NetworkCreate, db: AsyncSession = Depends(get_db)):
    try:
        user = await register_network(data.name, data.slug, data.email, data.password, db)
        return {"message": "Сеть создана", "user_id": str(user.id)}
    except Exception as e:
        logger.error("Registration error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login")
async def login(data: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
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
        max_age=60 * 60 * 24 * 30,
    )
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=False,
        samesite="lax",
        max_age=60 * settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    )
    return TokenResponse(access_token=access_token)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("refresh_token")
    return {"message": "Выход выполнен"}
