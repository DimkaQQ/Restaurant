import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, func, BigInteger, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    network_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("networks.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="manager")  # owner, manager, cashier, administrator
    venue_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("venues.id"), nullable=True, index=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    bot_link_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    # Brute-force lockout (per account, complements the per-IP rate limit)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Bumping revokes every outstanding JWT for this user (password reset etc.)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    # Station PIN (bcrypt hash): switch the acting employee on a shared tablet
    pin_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # TOTP 2FA: secret is provisional until the first code is confirmed
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # UI language — changed only from Settings, mirrored into the `lang` cookie
    language: Mapped[str] = mapped_column(String(5), default="ru", server_default="ru")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    network: Mapped["Network"] = relationship("Network", back_populates="users")
    venue: Mapped["Venue | None"] = relationship("Venue")

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"
