"""Staff bot auth, order comments, table number, status log, online ordering

Revision ID: 007
Revises: 006
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade():
    # order_items: per-item comment
    op.add_column('order_items', sa.Column('comment', sa.Text(), nullable=True))

    # orders: table number + source
    op.add_column('orders', sa.Column('table_number', sa.String(20), nullable=True))
    op.add_column('orders', sa.Column('source', sa.String(20), nullable=True, server_default='bot'))

    # order status audit log
    op.create_table(
        'order_status_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('order_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('old_status', sa.String(50), nullable=True),
        sa.Column('new_status', sa.String(50), nullable=False),
        sa.Column('changed_by', sa.String(255), nullable=True),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_order_status_log_order_id', 'order_status_log', ['order_id'])

    # users: link Telegram account (for staff bot)
    op.add_column('users', sa.Column('telegram_id', sa.BigInteger(), nullable=True))
    op.add_column('users', sa.Column('bot_link_token', sa.String(64), nullable=True))
    op.create_unique_constraint('uq_users_telegram_id', 'users', ['telegram_id'])
    op.create_unique_constraint('uq_users_bot_link_token', 'users', ['bot_link_token'])


def downgrade():
    op.drop_constraint('uq_users_bot_link_token', 'users', type_='unique')
    op.drop_constraint('uq_users_telegram_id', 'users', type_='unique')
    op.drop_column('users', 'bot_link_token')
    op.drop_column('users', 'telegram_id')
    op.drop_index('ix_order_status_log_order_id', 'order_status_log')
    op.drop_table('order_status_log')
    op.drop_column('orders', 'source')
    op.drop_column('orders', 'table_number')
    op.drop_column('order_items', 'comment')
