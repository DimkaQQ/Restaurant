"""Per-user UI language (changed only from Settings, synced to the `lang`
cookie on login and on change).

Revision ID: 031
Revises: 030
"""
import sqlalchemy as sa
from alembic import op

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("language", sa.String(5), nullable=False, server_default="ru"))


def downgrade():
    op.drop_column("users", "language")
