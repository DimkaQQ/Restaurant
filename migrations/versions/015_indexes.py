"""Add indexes on FK / commonly-filtered columns for multi-tenant scale.

Every query in this app filters by network_id and/or venue_id (tenant
isolation) plus frequently by guest_id/order_id/status/created_at — none of
that was indexed before, so these all degrade to sequential scans as tenants
grow. CREATE INDEX CONCURRENTLY isn't used here because Alembic runs each
migration inside a transaction by default; on a live DB with meaningful
row counts, run these statements manually with CONCURRENTLY instead.

Revision ID: 015
Revises: 014
"""
from alembic import op

revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None

# Some of these already exist from earlier migrations (001/002/004/005/007) —
# this list only adds what's genuinely still missing, cross-checked against
# every prior op.create_index call so upgrade() doesn't collide.
_INDEXES = [
    ("ix_expenses_network_id", "expenses", "network_id"),
    ("ix_expenses_created_by_id", "expenses", "created_by_id"),
    ("ix_guests_telegram_id", "guests", "telegram_id"),
    ("ix_guests_preferred_venue_id", "guests", "preferred_venue_id"),
    ("ix_ingredients_network_id", "ingredients", "network_id"),
    ("ix_writeoffs_ingredient_id", "writeoffs", "ingredient_id"),
    ("ix_writeoffs_created_by_id", "writeoffs", "created_by_id"),
    ("ix_orders_guest_id", "orders", "guest_id"),
    ("ix_orders_staff_id", "orders", "staff_id"),
    ("ix_orders_table_id", "orders", "table_id"),
    ("ix_orders_status", "orders", "status"),
    ("ix_orders_created_at", "orders", "created_at"),
    ("ix_order_items_order_id", "order_items", "order_id"),
    ("ix_order_items_menu_item_id", "order_items", "menu_item_id"),
    ("ix_visits_guest_id", "visits", "guest_id"),
    ("ix_visits_venue_id", "visits", "venue_id"),
    ("ix_visits_order_id", "visits", "order_id"),
    ("ix_points_transactions_guest_id", "points_transactions", "guest_id"),
    ("ix_points_transactions_venue_id", "points_transactions", "venue_id"),
    ("ix_recipes_menu_item_id", "recipes", "menu_item_id"),
    ("ix_recipes_ingredient_id", "recipes", "ingredient_id"),
    ("ix_reviews_order_id", "reviews", "order_id"),
    ("ix_reviews_guest_id", "reviews", "guest_id"),
    ("ix_shifts_staff_id", "shifts", "staff_id"),
    ("ix_users_network_id", "users", "network_id"),
    ("ix_users_venue_id", "users", "venue_id"),
    ("ix_venues_network_id", "venues", "network_id"),
    ("ix_tables_venue_id", "tables", "venue_id"),
    ("ix_subscriptions_status", "subscriptions", "status"),
]


def upgrade():
    for index_name, table, column in _INDEXES:
        op.create_index(index_name, table, [column])


def downgrade():
    for index_name, table, column in reversed(_INDEXES):
        op.drop_index(index_name, table_name=table)
