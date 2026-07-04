"""Waiter assignment on orders + queued Telegram notifications for staff.

Revision ID: 026
Revises: 025
"""
import sqlalchemy as sa
from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade():
    # Which login account (waiter/cashier) created the order — used for the
    # "my tables" filter on the waiter screen and ready-order notifications.
    op.add_column("orders", sa.Column("waiter_user_id", sa.UUID(), nullable=True))
    op.add_column("orders", sa.Column("waiter_name", sa.String(100), nullable=True))
    op.create_foreign_key(
        "fk_orders_waiter_user", "orders", "users",
        ["waiter_user_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_orders_waiter_user_id", "orders", ["waiter_user_id"])

    # Outbox for the Telegram bot: the server enqueues, the bot polls and
    # delivers (the bot owns the Telegram session, the server never does).
    op.create_table(
        "bot_notifications",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("network_id", sa.UUID(), sa.ForeignKey("networks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_bot_notifications_network_id", "bot_notifications", ["network_id"])
    op.create_index("ix_bot_notifications_delivered_at", "bot_notifications", ["delivered_at"])


def downgrade():
    op.drop_index("ix_bot_notifications_delivered_at", table_name="bot_notifications")
    op.drop_index("ix_bot_notifications_network_id", table_name="bot_notifications")
    op.drop_table("bot_notifications")
    op.drop_index("ix_orders_waiter_user_id", table_name="orders")
    op.drop_constraint("fk_orders_waiter_user", "orders", type_="foreignkey")
    op.drop_column("orders", "waiter_name")
    op.drop_column("orders", "waiter_user_id")
