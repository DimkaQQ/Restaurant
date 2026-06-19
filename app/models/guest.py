import uuid
from datetime import datetime
from sqlalchemy import String, BigInteger, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Guest(Base):
    __tablename__ = "guests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    network_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("networks.id"))
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    name: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    total_points: Mapped[int] = mapped_column(Integer, default=0)
    total_visits: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    network: Mapped["Network"] = relationship("Network", back_populates="guests")
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="guest")
    visits: Mapped[list["Visit"]] = relationship("Visit", back_populates="guest")
    points_transactions: Mapped[list["PointsTransaction"]] = relationship("PointsTransaction", back_populates="guest")
