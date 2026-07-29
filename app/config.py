from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost/restos"
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    ANTHROPIC_API_KEY: str = ""
    HTTPS_PROXY: str = ""
    API_URL: str = ""
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_STARTER: str = ""
    STRIPE_PRICE_PRO: str = ""
    STRIPE_PRICE_ENTERPRISE: str = ""
    PUBLIC_URL: str = "http://localhost:8000"
    # In-app support contact (surfaced in the sidebar and billing, referenced by
    # the legal docs). A Telegram/WhatsApp/website URL, or a mailto: link.
    SUPPORT_URL: str = "https://t.me/Dimka_Hum"
    # Display currency: the symbol shown across the app and the ISO code used for
    # Stripe checkouts. Defaults to Euro for the European market.
    CURRENCY: str = "€"
    CURRENCY_CODE: str = "eur"
    # Default UI language for visitors with no saved preference. English for the
    # European market; set to "ru" (etc.) for a Russian-first deployment.
    DEFAULT_LOCALE: str = "en"
    # Business-day timezone for reports («сегодня», periods, day charts)
    LOCAL_TZ: str = "Europe/Berlin"
    PLATFORM_ADMIN_EMAIL: str = ""
    SENTRY_DSN: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "RestOS <no-reply@restos.app>"
    RATE_LIMIT_ENABLED: bool = True
    CSRF_ENABLED: bool = True

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
