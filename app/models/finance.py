import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, Numeric, DateTime, Date, ForeignKey, func, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

EXPENSE_CATEGORIES = {
    "rent": "Аренда",
    "utilities": "Коммунальные",
    "salaries": "Зарплаты",
    "ingredients": "Продукты и напитки",
    "marketing": "Маркетинг",
    "equipment": "Оборудование",
    "other": "Прочее",
}


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    network_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("networks.id"))
    venue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venues.id"))
    category: Mapped[str] = mapped_column(String(50), default="other")
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    expense_date: Mapped[date] = mapped_column(Date)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    venue: Mapped["Venue"] = relationship("Venue", back_populates="expenses")

    @property
    def category_label(self) -> str:
        return EXPENSE_CATEGORIES.get(self.category, self.category)
