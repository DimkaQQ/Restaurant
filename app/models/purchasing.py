import uuid
from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import String, Numeric, DateTime, Date, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    network_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("networks.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PurchaseInvoice(Base):
    """A posted goods-receipt document: applying it increases stock and
    updates ingredient costs. Immutable once posted — accounting integrity."""
    __tablename__ = "purchase_invoices"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    venue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venues.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True)
    number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    invoice_date: Mapped[date] = mapped_column(Date)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    created_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    supplier: Mapped["Supplier | None"] = relationship("Supplier")
    lines: Mapped[list["PurchaseInvoiceLine"]] = relationship(
        "PurchaseInvoiceLine", back_populates="invoice", cascade="all, delete-orphan"
    )


class PurchaseInvoiceLine(Base):
    __tablename__ = "purchase_invoice_lines"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("purchase_invoices.id", ondelete="CASCADE"), index=True)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id", ondelete="CASCADE"))
    ingredient_name: Mapped[str] = mapped_column(String(255))  # snapshot for history
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    invoice: Mapped["PurchaseInvoice"] = relationship("PurchaseInvoice", back_populates="lines")
