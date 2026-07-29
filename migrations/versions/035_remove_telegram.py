"""Remove Telegram integration. The guest channel moves to a white-label PWA
(QR menu + install-to-home-screen), so all Telegram-specific columns and the
bot notification / broadcast tables are dropped.

Dropping a column in PostgreSQL also drops its indexes and unique constraints
(including the composite uq_guests_network_telegram), so those need no separate
step.

Revision ID: 035
Revises: 034
"""
import sqlalchemy as sa
from alembic import op

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("bot_notifications")
    op.drop_table("broadcasts")
    op.drop_column("guests", "telegram_id")
    op.drop_column("users", "telegram_id")
    op.drop_column("users", "bot_link_token")
    op.drop_column("venues", "telegram_bot_token")
    op.drop_column("venues", "manager_telegram_id")


def downgrade():
    op.add_column("venues", sa.Column("manager_telegram_id", sa.BigInteger(), nullable=True))
    op.add_column("venues", sa.Column("telegram_bot_token", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("bot_link_token", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("telegram_id", sa.BigInteger(), nullable=True))
    op.add_column("guests", sa.Column("telegram_id", sa.BigInteger(), nullable=True))
    op.create_unique_constraint("users_bot_link_token_key", "users", ["bot_link_token"])
    op.create_unique_constraint("users_telegram_id_key", "users", ["telegram_id"])
    op.create_index("ix_guests_telegram_id", "guests", ["telegram_id"])
    op.create_unique_constraint("uq_guests_network_telegram", "guests", ["network_id", "telegram_id"])
    op.create_table(
        "broadcasts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("network_id", sa.UUID(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("lang_filter", sa.String(5), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["network_id"], ["networks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "bot_notifications",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("network_id", sa.UUID(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["network_id"], ["networks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
