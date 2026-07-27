"""Per-item tile color (Square-style colored buttons on the register). Optional
— the POS "colored tiles" view is off by default and falls back to an
auto-assigned palette when an item has no color.

Revision ID: 033
Revises: 032
"""
import sqlalchemy as sa
from alembic import op

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("menu_items", sa.Column("color", sa.String(7), nullable=True))


def downgrade():
    op.drop_column("menu_items", "color")
