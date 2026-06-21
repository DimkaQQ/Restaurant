import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, DateTime, ForeignKey, func, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    network_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("networks.id"))
    venue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venues.id"))
    name: Mapped[str] = mapped_column(String(255))
    unit: Mapped[str] = mapped_column(String(20), default="кг")
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    min_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    cost_per_unit: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    venue: Mapped["Venue"] = relationship("Venue", back_populates="ingredients")
    writeoffs: Mapped[list["WriteOff"]] = relationship("WriteOff", back_populates="ingredient")

    @property
    def stock_status(self) -> str:
        if self.quantity <= 0:
            return "empty"
        if self.quantity <= self.min_quantity:
            return "low"
        if self.quantity <= self.min_quantity * 1.5:
            return "warning"
        return "ok"

    @property
    def total_value(self) -> Decimal:
        return self.quantity * self.cost_per_unit


class WriteOff(Base):
    __tablename__ = "writeoffs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    reason: Mapped[str] = mapped_column(String(50), default="usage")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ingredient: Mapped["Ingredient"] = relationship("Ingredient", back_populates="writeoffs")
