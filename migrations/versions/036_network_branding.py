"""White-label branding for the guest PWA: a network can set its own app name,
theme color and logo so the guest sees the restaurant's brand, not "RestOS".

Revision ID: 036
Revises: 035
"""
import sqlalchemy as sa
from alembic import op

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("networks", sa.Column("brand_name", sa.String(60), nullable=True))
    op.add_column("networks", sa.Column("brand_color", sa.String(7), nullable=True))
    op.add_column("networks", sa.Column("logo_url", sa.String(500), nullable=True))


def downgrade():
    op.drop_column("networks", "logo_url")
    op.drop_column("networks", "brand_color")
    op.drop_column("networks", "brand_name")
