"""Scope guest telegram_id uniqueness per network (security fix)

Guests were looked up/created by telegram_id alone with a GLOBAL unique
constraint, so a real customer visiting two unrelated restaurants (different
networks) on RestOS would collide into the same Guest row, and a network's
bot could query another network's guest/staff data by telegram_id with no
tenant check. This migration lets the same Telegram account have one Guest
row per network; app/routers/bot_api.py now requires network_id on every
telegram_id lookup.

Revision ID: 012
Revises: 011
"""
from alembic import op
import sqlalchemy as sa

revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('guests_telegram_id_key', 'guests', type_='unique')
    op.create_unique_constraint('uq_guests_network_telegram', 'guests', ['network_id', 'telegram_id'])


def downgrade():
    op.drop_constraint('uq_guests_network_telegram', 'guests', type_='unique')
    op.create_unique_constraint('guests_telegram_id_key', 'guests', ['telegram_id'])
