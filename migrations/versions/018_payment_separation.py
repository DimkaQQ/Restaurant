"""Separate payment from the order lifecycle.

status now tracks logistics only (done = served); payment_status/paid_at
track money. Historical done orders were paid under the old fused
semantics, so they are backfilled as paid.

Revision ID: 018
Revises: 017
"""
from alembic import op
import sqlalchemy as sa

revision = '018'
down_revision = '017'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('orders', sa.Column('payment_status', sa.String(20), nullable=False, server_default='unpaid'))
    op.add_column('orders', sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True))
    # Old semantics: reaching "done" implied payment was taken.
    op.execute(
        "UPDATE orders SET payment_status = 'paid', paid_at = updated_at WHERE status = 'done'"
    )
    op.create_index('ix_orders_payment_status', 'orders', ['payment_status'])


def downgrade():
    op.drop_index('ix_orders_payment_status', table_name='orders')
    op.drop_column('orders', 'paid_at')
    op.drop_column('orders', 'payment_status')
