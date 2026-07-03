import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, Numeric, Boolean, Integer, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PromoCode(Base):
    """Guest-facing promo codes for the QR menu (and staff POS). Value is a
    percent or a fixed amount off the order subtotal."""
    __tablename__ = "promo_codes"
    __table_args__ = (UniqueConstraint("network_id", "code", name="uq_promo_network_code"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    network_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("networks.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(50))  # stored uppercase
    type: Mapped[str] = mapped_column(String(10))  # percent | amount
    value: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
