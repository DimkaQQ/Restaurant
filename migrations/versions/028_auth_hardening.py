"""Auth hardening: per-account brute-force lockout + session revocation.

Revision ID: 028
Revises: 027
"""
import sqlalchemy as sa
from alembic import op

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade():
    # Brute-force lockout: counted per account (the per-IP rate limit alone
    # doesn't stop an attacker rotating IPs against one email).
    op.add_column("users", sa.Column("failed_logins", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    # Session revocation: JWTs carry this version; bumping it kills every
    # outstanding token (password reset, "выйти на всех устройствах").
    op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    op.drop_column("users", "token_version")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_logins")
