"""Per-venue, per-surface appearance (theme + accent for kitchen/pos/etc).

Revision ID: 030
Revises: 029
"""
import sqlalchemy as sa
from alembic import op

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("venues", sa.Column("appearance", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    op.drop_column("venues", "appearance")
