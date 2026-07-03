"""Order discounts and promo codes.

Revision ID: 021
Revises: 020
"""
from alembic import op
import sqlalchemy as sa

revision = '021'
down_revision = '020'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('orders', sa.Column('subtotal_amount', sa.Numeric(10, 2), nullable=True))
    op.add_column('orders', sa.Column('discount_type', sa.String(10), nullable=True))
    op.add_column('orders', sa.Column('discount_value', sa.Numeric(10, 2), nullable=True))
    op.add_column('orders', sa.Column('promo_code', sa.String(50), nullable=True))
    op.create_table(
        'promo_codes',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('network_id', sa.UUID(), sa.ForeignKey('networks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('type', sa.String(10), nullable=False),
        sa.Column('value', sa.Numeric(10, 2), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('max_uses', sa.Integer(), nullable=True),
        sa.Column('used_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('network_id', 'code', name='uq_promo_network_code'),
    )
    op.create_index('ix_promo_codes_network_id', 'promo_codes', ['network_id'])


def downgrade():
    op.drop_index('ix_promo_codes_network_id', table_name='promo_codes')
    op.drop_table('promo_codes')
    op.drop_column('orders', 'promo_code')
    op.drop_column('orders', 'discount_value')
    op.drop_column('orders', 'discount_type')
    op.drop_column('orders', 'subtotal_amount')
