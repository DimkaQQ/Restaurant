import uuid
from datetime import datetime
from sqlalchemy import String, Text, SmallInteger, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    venue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venues.id"))
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    guest_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("guests.id"), nullable=True)
    staff_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    food_rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    service_rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    overall_rating: Mapped[int] = mapped_column(SmallInteger)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="bot")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    venue: Mapped["Venue"] = relationship("Venue", back_populates="reviews")
    order: Mapped["Order | None"] = relationship("Order", back_populates="review")
    guest: Mapped["Guest | None"] = relationship("Guest", back_populates="reviews")
    staff: Mapped["Staff | None"] = relationship("Staff", back_populates="reviews")
