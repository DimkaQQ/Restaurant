"""Public API keys and outbound webhook subscriptions.

Revision ID: 025
Revises: 024
"""
from alembic import op
import sqlalchemy as sa

revision = '025'
down_revision = '024'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'api_keys',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('network_id', sa.UUID(), sa.ForeignKey('networks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('key_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('prefix', sa.String(12), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_api_keys_network_id', 'api_keys', ['network_id'])
    op.create_table(
        'webhook_subscriptions',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('network_id', sa.UUID(), sa.ForeignKey('networks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('url', sa.String(500), nullable=False),
        sa.Column('secret', sa.String(64), nullable=False),
        sa.Column('events', sa.String(200), nullable=False, server_default='order.created'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_webhook_subscriptions_network_id', 'webhook_subscriptions', ['network_id'])


def downgrade():
    op.drop_index('ix_webhook_subscriptions_network_id', table_name='webhook_subscriptions')
    op.drop_table('webhook_subscriptions')
    op.drop_index('ix_api_keys_network_id', table_name='api_keys')
    op.drop_table('api_keys')
