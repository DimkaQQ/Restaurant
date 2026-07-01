from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost/restos"
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    ANTHROPIC_API_KEY: str = ""
    BOT_TOKEN_VENUE_1: str = ""
    BOT_TOKEN_VENUE_2: str = ""
    NETWORK_ID: str = ""
    VENUE_ID_1: str = ""
    VENUE_ID_2: str = ""
    HTTPS_PROXY: str = ""
    TELEGRAM_API_SERVER: str = ""
    API_URL: str = ""
    BOT_NAME: str = ""
    BOT_API_SECRET: str = ""
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_STARTER: str = ""
    STRIPE_PRICE_PRO: str = ""
    STRIPE_PRICE_ENTERPRISE: str = ""
    PUBLIC_URL: str = "http://localhost:8000"
    PLATFORM_ADMIN_EMAIL: str = ""
    SENTRY_DSN: str = ""

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
