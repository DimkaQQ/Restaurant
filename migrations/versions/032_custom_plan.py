"""Build-your-own subscription: store the chosen modules and extra venues so a
network can assemble a custom plan instead of picking a fixed tier.

Revision ID: 032
Revises: 031
"""
import sqlalchemy as sa
from alembic import op

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("subscriptions", sa.Column("features", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("subscriptions", sa.Column("extra_venues", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("subscriptions", "extra_venues")
    op.drop_column("subscriptions", "features")
