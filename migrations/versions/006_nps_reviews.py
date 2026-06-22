"""nps reviews: venue manager_telegram_id, gis_url; order review_sent_at

Revision ID: 006
Revises: 005
Create Date: 2026-06-22 00:00:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("venues", sa.Column("manager_telegram_id", sa.BigInteger(), nullable=True))
    op.add_column("venues", sa.Column("gis_url", sa.String(500), nullable=True))
    op.add_column("orders", sa.Column("review_sent_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "review_sent_at")
    op.drop_column("venues", "gis_url")
    op.drop_column("venues", "manager_telegram_id")
