"""Client-generated idempotency key for offline-queued POS orders.

A tablet that lost connectivity queues orders locally and retries them
after reconnect; the unique key guarantees a retry can't create a
duplicate order.

Revision ID: 019
Revises: 018
"""
from alembic import op
import sqlalchemy as sa

revision = '019'
down_revision = '018'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('orders', sa.Column('client_order_id', sa.String(64), nullable=True))
    op.create_unique_constraint('uq_orders_client_order_id', 'orders', ['client_order_id'])


def downgrade():
    op.drop_constraint('uq_orders_client_order_id', 'orders', type_='unique')
    op.drop_column('orders', 'client_order_id')
