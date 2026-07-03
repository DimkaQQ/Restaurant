import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, Numeric, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CashShift(Base):
    """A cash-register session: opened with a counted drawer float, closed
    with a recount. Sales totals are snapshotted at close so the Z-report
    stays immutable even if orders are touched later. The expected/actual
    difference is the owner's primary anti-theft control."""
    __tablename__ = "cash_shifts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    venue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), index=True)
    opened_by: Mapped[str] = mapped_column(String(255))
    opening_cash: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    closed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closing_cash_actual: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Snapshot at close (Z-report)
    cash_sales: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    card_sales: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    orders_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_cash: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    difference: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
