"""bot features: language, preferred_venue, city, broadcasts

Revision ID: 005
Revises: 004
Create Date: 2026-06-21 00:00:00.000000

"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("guests", sa.Column("language", sa.String(5), nullable=False, server_default="ru"))
    op.add_column("guests", sa.Column("preferred_venue_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_guests_preferred_venue", "guests", "venues", ["preferred_venue_id"], ["id"])

    op.add_column("venues", sa.Column("city", sa.String(100), nullable=True))

    op.create_table(
        "broadcasts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("network_id", sa.UUID(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("lang_filter", sa.String(5), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["network_id"], ["networks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_broadcasts_network_id", "broadcasts", ["network_id"])


def downgrade() -> None:
    op.drop_table("broadcasts")
    op.drop_column("venues", "city")
    op.drop_constraint("fk_guests_preferred_venue", "guests", type_="foreignkey")
    op.drop_column("guests", "preferred_venue_id")
    op.drop_column("guests", "language")
