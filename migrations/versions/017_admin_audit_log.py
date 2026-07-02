"""Platform-admin audit trail (subscription overrides, impersonation).

Revision ID: 017
Revises: 016
"""
from alembic import op
import sqlalchemy as sa

revision = '017'
down_revision = '016'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'admin_audit_log',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('admin_email', sa.String(255), nullable=False),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('network_id', sa.UUID(), sa.ForeignKey('networks.id'), nullable=True),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_admin_audit_log_network_id', 'admin_audit_log', ['network_id'])


def downgrade():
    op.drop_index('ix_admin_audit_log_network_id', table_name='admin_audit_log')
    op.drop_table('admin_audit_log')
