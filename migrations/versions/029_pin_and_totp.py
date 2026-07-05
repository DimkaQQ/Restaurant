"""Station PINs (iiko-style operator switching) + TOTP 2FA for owners.

Revision ID: 029
Revises: 028
"""
import sqlalchemy as sa
from alembic import op

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade():
    # 4-6 digit PIN (bcrypt-hashed) for switching the acting employee on a
    # shared station tablet without typing an email/password.
    op.add_column("users", sa.Column("pin_hash", sa.String(255), nullable=True))
    # TOTP 2FA (RFC 6238): base32 secret + confirmed flag. Secret is set on
    # enrollment and only enforced after the user confirms a first code.
    op.add_column("users", sa.Column("totp_secret", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default="false"))


def downgrade():
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret")
    op.drop_column("users", "pin_hash")
