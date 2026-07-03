"""Tenant-scoped staff audit trail.

Revision ID: 024
Revises: 023
"""
from alembic import op
import sqlalchemy as sa

revision = '024'
down_revision = '023'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'staff_audit_log',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('network_id', sa.UUID(), sa.ForeignKey('networks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_email', sa.String(255), nullable=False),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_staff_audit_log_network_id', 'staff_audit_log', ['network_id'])
    op.create_index('ix_staff_audit_log_created_at', 'staff_audit_log', ['created_at'])


def downgrade():
    op.drop_index('ix_staff_audit_log_created_at', table_name='staff_audit_log')
    op.drop_index('ix_staff_audit_log_network_id', table_name='staff_audit_log')
    op.drop_table('staff_audit_log')
