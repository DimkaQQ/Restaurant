import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    network_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("networks.id"), unique=True)
    plan: Mapped[str] = mapped_column(String(50), default="starter")  # starter, pro, enterprise
    status: Mapped[str] = mapped_column(String(20), default="trial")  # trial, active, past_due, suspended, cancelled
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    network: Mapped["Network"] = relationship("Network", back_populates="subscription")

    @property
    def is_active(self) -> bool:
        return self.status in ("trial", "active")
