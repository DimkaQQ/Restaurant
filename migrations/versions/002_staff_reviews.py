"""staff and reviews

Revision ID: 002
Revises: 001
Create Date: 2026-06-20 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "staff",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("network_id", sa.UUID(), nullable=False),
        sa.Column("venue_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="waiter"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("avg_rating", sa.Float(), nullable=True),
        sa.Column("total_reviews", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["network_id"], ["networks.id"]),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_staff_network_id", "staff", ["network_id"])
    op.create_index("ix_staff_venue_id", "staff", ["venue_id"])

    op.add_column("orders", sa.Column("staff_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_orders_staff_id", "orders", "staff", ["staff_id"], ["id"])

    op.create_table(
        "reviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("venue_id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=True),
        sa.Column("guest_id", sa.UUID(), nullable=True),
        sa.Column("staff_id", sa.UUID(), nullable=True),
        sa.Column("food_rating", sa.SmallInteger(), nullable=True),
        sa.Column("service_rating", sa.SmallInteger(), nullable=True),
        sa.Column("overall_rating", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("source", sa.String(50), nullable=False, server_default="bot"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["venue_id"], ["venues.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["guest_id"], ["guests.id"]),
        sa.ForeignKeyConstraint(["staff_id"], ["staff.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reviews_venue_id", "reviews", ["venue_id"])
    op.create_index("ix_reviews_staff_id", "reviews", ["staff_id"])


def downgrade() -> None:
    op.drop_table("reviews")
    op.drop_constraint("fk_orders_staff_id", "orders", type_="foreignkey")
    op.drop_column("orders", "staff_id")
    op.drop_table("staff")
