"""Cash register shifts with Z-report snapshot.

Revision ID: 022
Revises: 021
"""
from alembic import op
import sqlalchemy as sa

revision = '022'
down_revision = '021'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cash_shifts',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('venue_id', sa.UUID(), sa.ForeignKey('venues.id', ondelete='CASCADE'), nullable=False),
        sa.Column('opened_by', sa.String(255), nullable=False),
        sa.Column('opening_cash', sa.Numeric(10, 2), nullable=False, server_default='0'),
        sa.Column('opened_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('closed_by', sa.String(255), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('closing_cash_actual', sa.Numeric(10, 2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('cash_sales', sa.Numeric(10, 2), nullable=True),
        sa.Column('card_sales', sa.Numeric(10, 2), nullable=True),
        sa.Column('orders_count', sa.Integer(), nullable=True),
        sa.Column('expected_cash', sa.Numeric(10, 2), nullable=True),
        sa.Column('difference', sa.Numeric(10, 2), nullable=True),
    )
    op.create_index('ix_cash_shifts_venue_id', 'cash_shifts', ['venue_id'])


def downgrade():
    op.drop_index('ix_cash_shifts_venue_id', table_name='cash_shifts')
    op.drop_table('cash_shifts')
