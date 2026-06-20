"""user venue assignment

Revision ID: 003
Revises: 002
Create Date: 2026-06-20 00:00:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("venue_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_users_venue_id", "users", "venues", ["venue_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_users_venue_id", "users", type_="foreignkey")
    op.drop_column("users", "venue_id")
