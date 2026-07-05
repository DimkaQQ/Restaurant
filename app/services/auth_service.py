import logging
import uuid
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.network import Network
from app.models.user import User
from app.models.subscription import Subscription

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict) -> str:
    payload = data.copy()
    # typ marks this as a refresh token: it can only be exchanged for a new
    # access token, never used directly as one (see get_current_user).
    payload["typ"] = "refresh"
    payload["exp"] = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


async def get_current_user(token: str, db: AsyncSession) -> User | None:
    payload = decode_token(token)
    if not payload:
        return None
    # A refresh token is not a session: it may only pass through the
    # explicit exchange path (refresh_session), never authenticate directly.
    if payload.get("typ") == "refresh":
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    # Version check: bumping user.token_version (password reset, forced
    # logout) instantly revokes every token minted before the bump.
    if user and payload.get("ver", 0) != (user.token_version or 0):
        return None
    return user


async def refresh_session(refresh_token: str, db: AsyncSession) -> tuple[User, str] | None:
    """Exchange a valid refresh token for a fresh access token. Returns
    (user, new_access_token) or None. Keeps workstation tablets logged in
    without long-lived access tokens."""
    payload = decode_token(refresh_token)
    if not payload or payload.get("typ") != "refresh":
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    user = (await db.execute(select(User).where(User.id == uuid.UUID(user_id)))).scalar_one_or_none()
    if not user or payload.get("ver", 0) != (user.token_version or 0):
        return None
    return user, create_access_token({"sub": str(user.id), "ver": user.token_version or 0})


async def register_network(name: str, slug: str, email: str, password: str, db: AsyncSession) -> User:
    network = Network(id=uuid.uuid4(), name=name, slug=slug)
    db.add(network)
    await db.flush()

    user = User(
        id=uuid.uuid4(),
        network_id=network.id,
        email=email,
        hashed_password=hash_password(password),
        role="owner",
    )
    db.add(user)

    subscription = Subscription(
        id=uuid.uuid4(),
        network_id=network.id,
        plan="starter",
        status="trial",
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
    )
    db.add(subscription)

    await db.commit()
    await db.refresh(user)
    logger.info("Registered network %s with owner %s (14-day trial)", slug, email)
    return user


async def authenticate_user(email: str, password: str, db: AsyncSession) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def create_password_reset_token(user: User, expire_minutes: int = 30) -> str:
    # Bind the token to the current password hash so it's invalidated the
    # moment it's used (or the password is changed some other way) — a
    # stateless JWT alone would stay valid and replayable until it expires.
    # Staff invites reuse this same token type with a longer expiry instead
    # of a separate mechanism (see routers/settings.py create_user).
    payload = {
        "sub": str(user.id),
        "purpose": "password_reset",
        "pw": user.hashed_password[-16:],
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expire_minutes),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def verify_password_reset_token(token: str, db: AsyncSession) -> User | None:
    payload = decode_token(token)
    if not payload or payload.get("purpose") != "password_reset":
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or user.hashed_password[-16:] != payload.get("pw"):
        return None
    return user


def create_email_verification_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "purpose": "email_verify",
        "exp": datetime.now(timezone.utc) + timedelta(days=3),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def verify_email_token(token: str, db: AsyncSession) -> User | None:
    payload = decode_token(token)
    if not payload or payload.get("purpose") != "email_verify":
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    return result.scalar_one_or_none()
