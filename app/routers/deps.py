from fastapi import Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.auth_service import get_current_user


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept


async def get_current_user_dep(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    if not token:
        token = request.cookies.get("access_token")

    if not token:
        if _wants_html(request):
            raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/auth/login"})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Не авторизован")

    user = await get_current_user(token, db)
    if not user:
        if _wants_html(request):
            raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/auth/login"})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительный токен")
    return user


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    try:
        return await get_current_user_dep(request, db)
    except HTTPException:
        return None


async def get_accessible_venue_ids(user: User, db: AsyncSession) -> list:
    from sqlalchemy import select
    from app.models.venue import Venue
    stmt = select(Venue.id).where(Venue.network_id == user.network_id, Venue.is_active == True)
    if user.role != "owner":
        if user.venue_id:
            stmt = stmt.where(Venue.id == user.venue_id)
        else:
            return []
    result = await db.execute(stmt)
    return list(result.scalars().all())
