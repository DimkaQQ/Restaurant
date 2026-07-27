import uuid
from sqlalchemy import String, Text, Numeric, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from decimal import Decimal


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    venue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venues.id"))  # indexed as ix_menu_items_venue (migration 001)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    category: Mapped[str | None] = mapped_column(String(100))
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    image_url: Mapped[str | None] = mapped_column(String(500))
    # Optional tile color (hex) for the Square-style colored register view.
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)

    venue: Mapped["Venue"] = relationship("Venue", back_populates="menu_items")
    order_items: Mapped[list["OrderItem"]] = relationship("OrderItem", back_populates="menu_item")
    recipes: Mapped[list["Recipe"]] = relationship("Recipe", back_populates="menu_item", cascade="all, delete-orphan")
    modifier_groups: Mapped[list["ModifierGroup"]] = relationship(
        "ModifierGroup", back_populates="menu_item", cascade="all, delete-orphan", order_by="ModifierGroup.sort"
    )


class ModifierGroup(Base):
    """A choice attached to a menu item: 'Размер' (required, pick one),
    'Сиропы' (optional, pick many). Options carry price deltas."""
    __tablename__ = "modifier_groups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    menu_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("menu_items.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    required: Mapped[bool] = mapped_column(Boolean, default=False)   # must pick exactly one
    multi: Mapped[bool] = mapped_column(Boolean, default=False)      # allow picking several
    sort: Mapped[int] = mapped_column(default=0)

    menu_item: Mapped["MenuItem"] = relationship("MenuItem", back_populates="modifier_groups")
    options: Mapped[list["ModifierOption"]] = relationship(
        "ModifierOption", back_populates="group", cascade="all, delete-orphan", order_by="ModifierOption.sort"
    )


class ModifierOption(Base):
    __tablename__ = "modifier_options"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("modifier_groups.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    price_delta: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    sort: Mapped[int] = mapped_column(default=0)

    group: Mapped["ModifierGroup"] = relationship("ModifierGroup", back_populates="options")
