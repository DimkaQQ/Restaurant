import uuid
from decimal import Decimal
from sqlalchemy import Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Recipe(Base):
    """Tech card: how much of an ingredient one unit of a menu item consumes."""
    __tablename__ = "recipes"
    __table_args__ = (UniqueConstraint("menu_item_id", "ingredient_id", name="uq_recipe_item_ingredient"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    menu_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("menu_items.id", ondelete="CASCADE"))
    ingredient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingredients.id", ondelete="CASCADE"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3))

    menu_item: Mapped["MenuItem"] = relationship("MenuItem", back_populates="recipes")
    ingredient: Mapped["Ingredient"] = relationship("Ingredient")
