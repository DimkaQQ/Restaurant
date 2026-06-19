import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class PointsTransaction(Base):
    __tablename__ = "points_transactions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    guest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("guests.id"))
    venue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venues.id"))
    amount: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    guest: Mapped["Guest"] = relationship("Guest", back_populates="points_transactions")
    venue: Mapped["Venue"] = relationship("Venue", back_populates="points_transactions")
