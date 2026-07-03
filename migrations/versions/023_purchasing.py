"""Suppliers and purchase invoices (goods receipts).

Revision ID: 023
Revises: 022
"""
from alembic import op
import sqlalchemy as sa

revision = '023'
down_revision = '022'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'suppliers',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('network_id', sa.UUID(), sa.ForeignKey('networks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_suppliers_network_id', 'suppliers', ['network_id'])
    op.create_table(
        'purchase_invoices',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('venue_id', sa.UUID(), sa.ForeignKey('venues.id', ondelete='CASCADE'), nullable=False),
        sa.Column('supplier_id', sa.UUID(), sa.ForeignKey('suppliers.id', ondelete='SET NULL'), nullable=True),
        sa.Column('number', sa.String(100), nullable=True),
        sa.Column('invoice_date', sa.Date(), nullable=False),
        sa.Column('total', sa.Numeric(12, 2), nullable=False, server_default='0'),
        sa.Column('created_by', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_purchase_invoices_venue_id', 'purchase_invoices', ['venue_id'])
    op.create_table(
        'purchase_invoice_lines',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('invoice_id', sa.UUID(), sa.ForeignKey('purchase_invoices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ingredient_id', sa.UUID(), sa.ForeignKey('ingredients.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ingredient_name', sa.String(255), nullable=False),
        sa.Column('quantity', sa.Numeric(12, 3), nullable=False),
        sa.Column('unit_cost', sa.Numeric(10, 2), nullable=False),
    )
    op.create_index('ix_purchase_invoice_lines_invoice_id', 'purchase_invoice_lines', ['invoice_id'])


def downgrade():
    op.drop_index('ix_purchase_invoice_lines_invoice_id', table_name='purchase_invoice_lines')
    op.drop_table('purchase_invoice_lines')
    op.drop_index('ix_purchase_invoices_venue_id', table_name='purchase_invoices')
    op.drop_table('purchase_invoices')
    op.drop_index('ix_suppliers_network_id', table_name='suppliers')
    op.drop_table('suppliers')
