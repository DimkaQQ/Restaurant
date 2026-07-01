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
    user_id = payload.get("sub")
    if not user_id:
        return None
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    return result.scalar_one_or_none()


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
