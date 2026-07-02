"""Fiscal receipt integration: per-venue kassa credentials, per-order fiscal status

Revision ID: 014
Revises: 013
"""
from alembic import op
import sqlalchemy as sa

revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('venues', sa.Column('fiscal_provider', sa.String(30), nullable=True))
    op.add_column('venues', sa.Column('fiscal_api_key', sa.String(255), nullable=True))
    op.add_column('venues', sa.Column('fiscal_login', sa.String(255), nullable=True))
    op.add_column('venues', sa.Column('fiscal_password', sa.String(255), nullable=True))
    op.add_column('venues', sa.Column('fiscal_cashbox_number', sa.String(100), nullable=True))

    op.add_column('orders', sa.Column('payment_method', sa.String(20), nullable=True))
    op.add_column('orders', sa.Column('fiscal_status', sa.String(20), nullable=True))
    op.add_column('orders', sa.Column('fiscal_check_number', sa.String(100), nullable=True))
    op.add_column('orders', sa.Column('fiscal_ticket_url', sa.String(500), nullable=True))
    op.add_column('orders', sa.Column('fiscal_error', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('orders', 'fiscal_error')
    op.drop_column('orders', 'fiscal_ticket_url')
    op.drop_column('orders', 'fiscal_check_number')
    op.drop_column('orders', 'fiscal_status')
    op.drop_column('orders', 'payment_method')

    op.drop_column('venues', 'fiscal_cashbox_number')
    op.drop_column('venues', 'fiscal_password')
    op.drop_column('venues', 'fiscal_login')
    op.drop_column('venues', 'fiscal_api_key')
    op.drop_column('venues', 'fiscal_provider')
