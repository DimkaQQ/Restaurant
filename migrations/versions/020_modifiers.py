"""Menu item modifiers: size/milk/syrup options with price deltas.

Revision ID: 020
Revises: 019
"""
from alembic import op
import sqlalchemy as sa

revision = '020'
down_revision = '019'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'modifier_groups',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('menu_item_id', sa.UUID(), sa.ForeignKey('menu_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('required', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('multi', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('sort', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_index('ix_modifier_groups_menu_item_id', 'modifier_groups', ['menu_item_id'])
    op.create_table(
        'modifier_options',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('group_id', sa.UUID(), sa.ForeignKey('modifier_groups.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('price_delta', sa.Numeric(10, 2), nullable=False, server_default='0'),
        sa.Column('sort', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_index('ix_modifier_options_group_id', 'modifier_options', ['group_id'])
    op.add_column('order_items', sa.Column('modifiers', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('order_items', 'modifiers')
    op.drop_index('ix_modifier_options_group_id', table_name='modifier_options')
    op.drop_table('modifier_options')
    op.drop_index('ix_modifier_groups_menu_item_id', table_name='modifier_groups')
    op.drop_table('modifier_groups')
