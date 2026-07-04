"""One open cash shift per venue, enforced by the database.

The application checks before opening, but two concurrent opens can both
pass the check (SELECT ... FOR UPDATE on zero rows locks nothing). A partial
unique index makes the invariant hold under any concurrency.

Revision ID: 027
Revises: 026
"""
import sqlalchemy as sa  # noqa: F401
from alembic import op

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_cash_shifts_open_per_venue "
        "ON cash_shifts (venue_id) WHERE closed_at IS NULL"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_cash_shifts_open_per_venue")
