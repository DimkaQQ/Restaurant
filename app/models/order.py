import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Text, Numeric, Integer, DateTime, ForeignKey, func, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    venue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venues.id"))
    guest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("guests.id"))
    staff_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="new")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    points_earned: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    table_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    table_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tables.id", ondelete="SET NULL"), nullable=True)
    source: Mapped[str | None] = mapped_column(String(20), nullable=True, default='bot')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    review_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    venue: Mapped["Venue"] = relationship("Venue", back_populates="orders")
    guest: Mapped["Guest"] = relationship("Guest", back_populates="orders")
    staff: Mapped["Staff | None"] = relationship("Staff", back_populates="orders")
    table: Mapped["Table | None"] = relationship("Table")
    items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    status_log: Mapped[list["OrderStatusLog"]] = relationship("OrderStatusLog", back_populates="order", cascade="all, delete-orphan")
    visit: Mapped["Visit | None"] = relationship("Visit", back_populates="order", uselist=False)
    review: Mapped["Review | None"] = relationship("Review", back_populates="order", uselist=False)


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"))
    menu_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("menu_items.id"), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    name: Mapped[str] = mapped_column(String(255))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="items")
    menu_item: Mapped["MenuItem | None"] = relationship("MenuItem", back_populates="order_items")


class Visit(Base):
    __tablename__ = "visits"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    guest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("guests.id"))
    venue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venues.id"))
    order_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    visited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    guest: Mapped["Guest"] = relationship("Guest", back_populates="visits")
    venue: Mapped["Venue"] = relationship("Venue", back_populates="visits")
    order: Mapped["Order | None"] = relationship("Order", back_populates="visit")


class OrderStatusLog(Base):
    __tablename__ = "order_status_log"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    old_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    new_status: Mapped[str] = mapped_column(String(50))
    changed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    order: Mapped["Order"] = relationship("Order", back_populates="status_log")
