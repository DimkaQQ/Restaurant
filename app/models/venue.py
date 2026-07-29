import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Text, DateTime, ForeignKey, func, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Venue(Base):
    __tablename__ = "venues"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    network_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("networks.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gis_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Fiscal receipt integration (KZ online kassa providers, e.g. Webkassa) —
    # each venue has its own registered kassa/ОФД, credentials are per-venue.
    fiscal_provider: Mapped[str | None] = mapped_column(String(30), nullable=True)  # None, "webkassa"
    fiscal_api_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fiscal_login: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fiscal_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fiscal_cashbox_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Per-surface appearance: {"kitchen": {"theme": "light", "accent": "#5B8DEF"}, "pos": {...}, ...}
    appearance: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")

    network: Mapped["Network"] = relationship("Network", back_populates="venues")
    menu_items: Mapped[list["MenuItem"]] = relationship("MenuItem", back_populates="venue")
    orders: Mapped[list["Order"]] = relationship("Order", back_populates="venue")
    visits: Mapped[list["Visit"]] = relationship("Visit", back_populates="venue")
    points_transactions: Mapped[list["PointsTransaction"]] = relationship("PointsTransaction", back_populates="venue")
    staff: Mapped[list["Staff"]] = relationship("Staff", back_populates="venue")
    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="venue")
    ingredients: Mapped[list["Ingredient"]] = relationship("Ingredient", back_populates="venue")
    expenses: Mapped[list["Expense"]] = relationship("Expense", back_populates="venue")
    shifts: Mapped[list["Shift"]] = relationship("Shift", back_populates="venue")
    tables: Mapped[list["Table"]] = relationship("Table", back_populates="venue", cascade="all, delete-orphan")
