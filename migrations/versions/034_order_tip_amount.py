"""Gratuity (Square-style tips) on orders. Stored separately from
total_amount so revenue reports stay clean; cash tips are added to the
drawer's expected cash at shift close.

Revision ID: 034
Revises: 033
"""
import sqlalchemy as sa
from alembic import op

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "orders",
        sa.Column("tip_amount", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("orders", "tip_amount")
