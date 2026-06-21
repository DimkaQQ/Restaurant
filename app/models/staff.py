import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Float, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

ROLE_LABELS = {
    "waiter": "Официант",
    "senior_waiter": "Ст. официант",
    "manager": "Менеджер",
    "bartender": "Бармен",
    "barista": "Бариста",
    "hostess": "Хостес",
}


class Staff(Base):
    __tablename__ = "staff"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    network_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("networks.id"))
    venue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venues.id"))
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="waiter")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    avg_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_reviews: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    venue: Mapped["Venue"] = relationship("Venue", back_populates="staff")
    network: Mapped["Network"] = relationship("Network", back_populates="staff")
    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="staff")
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="staff")
    shifts: Mapped[list["Shift"]] = relationship("Shift", back_populates="staff")

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, self.role)

    @property
    def initials(self) -> str:
        parts = self.name.split()
        return "".join(p[0] for p in parts[:2]).upper()
