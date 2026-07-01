"""Tables: physical table management (free/occupied/reserved) for the POS

Revision ID: 011
Revises: 010
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tables',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('venue_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('label', sa.String(20), nullable=False),
        sa.Column('seats', sa.Integer(), nullable=False, server_default='4'),
        sa.Column('status', sa.String(20), nullable=False, server_default='free'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['venue_id'], ['venues.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.add_column('orders', sa.Column('table_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_orders_table_id', 'orders', 'tables', ['table_id'], ['id'], ondelete='SET NULL'
    )


def downgrade():
    op.drop_constraint('fk_orders_table_id', 'orders', type_='foreignkey')
    op.drop_column('orders', 'table_id')
    op.drop_table('tables')
