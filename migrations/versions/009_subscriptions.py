"""Subscription/billing table for SaaS trial and plan management

Revision ID: 009
Revises: 008
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'subscriptions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('network_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('plan', sa.String(50), nullable=False, server_default='starter'),
        sa.Column('status', sa.String(20), nullable=False, server_default='trial'),
        sa.Column('trial_ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('stripe_customer_id', sa.String(255), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['network_id'], ['networks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('network_id', name='uq_subscriptions_network'),
    )

    # Backfill: existing networks get an active subscription so current
    # tenants (e.g. Daniyar's network) are never locked out by this migration.
    op.execute("""
        INSERT INTO subscriptions (id, network_id, plan, status)
        SELECT gen_random_uuid(), id, 'enterprise', 'active' FROM networks
    """)


def downgrade():
    op.drop_table('subscriptions')
