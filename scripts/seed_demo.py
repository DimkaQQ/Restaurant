"""
Demo tenant: a ready-to-show account with a fully populated dashboard and
every page filled — orders, revenue, analytics, finance, inventory, guests,
reviews, staff, shifts and cash shifts. European branding, EUR prices, and all
history anchored to *now* so the dashboard looks live the moment you log in.

The demo network is created on a trial subscription, so every feature
(analytics, finance, white-label, API) is unlocked for the walkthrough.

Usage:
  python scripts/seed_demo.py            # create/refresh the demo tenant
  python scripts/seed_demo.py --force    # same (kept for symmetry with seed_data)

Login (override with env DEMO_EMAIL / DEMO_PASSWORD):
  email:    demo@restos.app
  password: demo1234
"""
import asyncio
import os
import sys
import uuid
import random
from datetime import datetime, timedelta, timezone, date, time
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

import sqlalchemy as sa
from sqlalchemy import select, insert, text

from app.database import AsyncSessionLocal
from app.models.network import Network
from app.models.venue import Venue
from app.models.menu import MenuItem
from app.models.guest import Guest
from app.models.order import Order, OrderItem, Visit
from app.models.staff import Staff
from app.models.review import Review
from app.models.inventory import Ingredient, WriteOff
from app.models.finance import Expense
from app.models.shift import Shift
from app.models.table import Table
from app.models.cash_shift import CashShift
from app.models.user import User
from app.services.auth_service import hash_password
from app.models.subscription import Subscription

DEMO_SLUG = "demo"
DEMO_NAME = "Terra Bistro Group"
DEMO_EMAIL = os.getenv("DEMO_EMAIL", "demo@restos.app")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "demo1234")

HIST_DAYS = 75          # days of paid history behind today
random.seed(42)         # stable demo between runs


# ══════════════════════════════════════════════════════════════════════════════
# VENUES — a small European group: two bistros + one café concept
#   brand: "bistro" | "cafe"  ·  dmin/dmax: orders/day
# ══════════════════════════════════════════════════════════════════════════════
VENUES = [
    {"brand": "bistro", "name": "Terra Bistro — Mitte",        "city": "Berlin",  "address": "Torstraße 114",        "dmin": 55, "dmax": 95},
    {"brand": "bistro", "name": "Terra Bistro — Prenzlauer Berg", "city": "Berlin", "address": "Kastanienallee 47",  "dmin": 45, "dmax": 80},
    {"brand": "cafe",   "name": "Caffè Terra — Hamburg",        "city": "Hamburg", "address": "Schulterblatt 58",     "dmin": 70, "dmax": 120},
]

# name, category, price (EUR), weight (popularity)
MENU_BY_BRAND = {
    "bistro": [
        {"name": "Bruschetta al Pomodoro", "cat": "Starters", "price": 7.5,  "w": 8},
        {"name": "Burrata & Prosciutto",   "cat": "Starters", "price": 12.0, "w": 6},
        {"name": "Caesar Salad",           "cat": "Salads",   "price": 11.0, "w": 9},
        {"name": "Margherita Pizza",       "cat": "Pizza",    "price": 11.5, "w": 12},
        {"name": "Diavola Pizza",          "cat": "Pizza",    "price": 13.5, "w": 9},
        {"name": "Pasta Carbonara",        "cat": "Pasta",    "price": 14.0, "w": 13},
        {"name": "Tagliatelle al Ragù",    "cat": "Pasta",    "price": 15.0, "w": 8},
        {"name": "Risotto ai Funghi",      "cat": "Mains",    "price": 15.5, "w": 6},
        {"name": "Ribeye Steak 300g",      "cat": "Mains",    "price": 26.0, "w": 5},
        {"name": "Tiramisù",               "cat": "Desserts", "price": 7.0,  "w": 7},
        {"name": "Panna Cotta",            "cat": "Desserts", "price": 6.5,  "w": 5},
        {"name": "Espresso",               "cat": "Drinks",   "price": 2.5,  "w": 10},
        {"name": "Cappuccino",             "cat": "Drinks",   "price": 3.5,  "w": 8},
        {"name": "House Red (glass)",      "cat": "Drinks",   "price": 6.0,  "w": 9},
        {"name": "Aperol Spritz",          "cat": "Drinks",   "price": 8.5,  "w": 8},
        {"name": "Craft Lager 0.3l",       "cat": "Drinks",   "price": 5.0,  "w": 7},
    ],
    "cafe": [
        {"name": "Espresso",         "cat": "Coffee",    "price": 2.5, "w": 12},
        {"name": "Cappuccino",       "cat": "Coffee",    "price": 3.5, "w": 14},
        {"name": "Flat White",       "cat": "Coffee",    "price": 3.8, "w": 11},
        {"name": "Caffè Latte",      "cat": "Coffee",    "price": 4.0, "w": 10},
        {"name": "Matcha Latte",     "cat": "Coffee",    "price": 4.5, "w": 6},
        {"name": "Fresh Orange",     "cat": "Cold",      "price": 4.0, "w": 7},
        {"name": "Iced Latte",       "cat": "Cold",      "price": 4.2, "w": 8},
        {"name": "Butter Croissant", "cat": "Bakery",    "price": 3.0, "w": 12},
        {"name": "Pain au Chocolat", "cat": "Bakery",    "price": 3.3, "w": 9},
        {"name": "Avocado Toast",    "cat": "Breakfast", "price": 8.5, "w": 10},
        {"name": "Pancake Stack",    "cat": "Breakfast", "price": 9.0, "w": 8},
        {"name": "Granola Bowl",     "cat": "Breakfast", "price": 7.5, "w": 6},
        {"name": "Cheesecake",       "cat": "Bakery",    "price": 5.5, "w": 7},
        {"name": "Carrot Cake",      "cat": "Bakery",    "price": 5.0, "w": 5},
    ],
}

FIRST_NAMES = [
    "Anna", "Lena", "Marie", "Sofia", "Emma", "Julia", "Laura", "Clara", "Nina", "Elena",
    "Lukas", "Max", "Paul", "Jonas", "Leon", "Felix", "David", "Marco", "Luca", "Tom",
    "Sophie", "Hannah", "Mia", "Chiara", "Giulia", "Camille", "Léa", "Manon", "Nora", "Alba",
    "Matteo", "Andrea", "Pierre", "Antoine", "Diego", "Pablo", "Jan", "Niklas", "Finn", "Ben",
]
LAST_NAMES = [
    "Müller", "Schmidt", "Weber", "Wagner", "Becker", "Hoffmann", "Koch", "Richter", "Klein", "Wolf",
    "Rossi", "Ferrari", "Russo", "Bianchi", "Romano", "Greco", "Conti", "Costa", "Ricci", "Marino",
    "Dupont", "Martin", "Bernard", "Dubois", "Moreau", "Laurent", "García", "Fernández", "López", "Martínez",
]

COMMENTS_POSITIVE = [
    "Lovely food and a warm atmosphere.", "Best carbonara in the city, honestly.",
    "Great service, we'll be back for sure.", "Fast, friendly and delicious.",
    "The staff were so attentive. Thank you!", "Perfect spot for a relaxed evening.",
    "Everything was spot on.", "Generous portions, fair prices.",
    "Wonderful coffee and pastries.", "Cosy place, lovely team.",
]
COMMENTS_NEUTRAL = [
    "Good overall, could be a touch faster.", "Nice food, we waited a bit long.",
    "Pleasant spot but a little noisy.", "Decent, nothing extraordinary.",
    "Tasty, service could be quicker.",
]
COMMENTS_NEGATIVE = [
    "Waited too long for the order.", "Service felt a bit rushed.",
    "The dish didn't match the description.", "Expected more for the price.",
]


def rand_phone() -> str:
    return f"+49 1{random.randint(50, 79)} {random.randint(100, 999)} {random.randint(1000, 9999)}"


def full_name() -> str:
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


async def wipe_existing_demo(db, network_id: uuid.UUID) -> None:
    """Remove a previous demo tenant so re-running gives a clean account.
    Scoped strictly to the demo network via its venues/guests/ingredients."""
    v = "(SELECT id FROM venues WHERE network_id = :nid)"
    g = "(SELECT id FROM guests WHERE network_id = :nid)"
    ing = "(SELECT id FROM ingredients WHERE network_id = :nid)"
    o = f"(SELECT id FROM orders WHERE venue_id IN {v})"
    stmts = [
        f"DELETE FROM order_items WHERE order_id IN {o}",
        f"DELETE FROM reviews WHERE venue_id IN {v}",
        f"DELETE FROM visits WHERE venue_id IN {v}",
        f"DELETE FROM points_transactions WHERE guest_id IN {g}",
        f"DELETE FROM writeoffs WHERE ingredient_id IN {ing}",
        f"DELETE FROM shifts WHERE venue_id IN {v}",
        f"DELETE FROM cash_shifts WHERE venue_id IN {v}",
        f"DELETE FROM tables WHERE venue_id IN {v}",
        f"DELETE FROM orders WHERE venue_id IN {v}",
        "DELETE FROM ingredients WHERE network_id = :nid",
        "DELETE FROM expenses WHERE network_id = :nid",
        f"DELETE FROM menu_items WHERE venue_id IN {v}",
        "DELETE FROM staff WHERE network_id = :nid",
        "DELETE FROM guests WHERE network_id = :nid",
        "UPDATE users SET venue_id = NULL WHERE network_id = :nid",
        "DELETE FROM users WHERE network_id = :nid",
        "DELETE FROM subscriptions WHERE network_id = :nid",
        "DELETE FROM venues WHERE network_id = :nid",
        "DELETE FROM networks WHERE id = :nid",
    ]
    for s in stmts:
        await db.execute(text(s), {"nid": network_id})
    await db.commit()


async def main():
    now = datetime.now(timezone.utc)
    today = date.today()

    async with AsyncSessionLocal() as db:
        # ── Fresh start: drop any prior demo tenant ──────────────────────────
        existing = (await db.execute(
            select(Network).where(Network.slug == DEMO_SLUG)
        )).scalar_one_or_none()
        if existing:
            print("   Removing previous demo tenant...")
            await wipe_existing_demo(db, existing.id)

        # ── Network + owner + trial subscription (all features unlocked) ─────
        network = Network(id=uuid.uuid4(), name=DEMO_NAME, slug=DEMO_SLUG)
        db.add(network)
        await db.flush()
        owner = User(
            id=uuid.uuid4(), network_id=network.id, email=DEMO_EMAIL,
            hashed_password=hash_password(DEMO_PASSWORD), role="owner",
        )
        db.add(owner)
        db.add(Subscription(
            id=uuid.uuid4(), network_id=network.id, plan="starter", status="trial",
            trial_ends_at=now + timedelta(days=3650),
        ))
        await db.commit()
        print(f"✅ Demo tenant: {DEMO_NAME}  ({DEMO_EMAIL} / {DEMO_PASSWORD})")

        # ── Venues ───────────────────────────────────────────────────────────
        venue_rows, venue_meta = [], []
        for v in VENUES:
            vid = uuid.uuid4()
            venue_rows.append({
                "id": vid, "network_id": network.id, "name": v["name"],
                "address": f"{v['address']}, {v['city']}", "is_active": True,
                "created_at": now - timedelta(days=random.randint(300, 700)),
            })
            venue_meta.append({**v, "id": vid})
        await db.execute(insert(Venue), venue_rows)
        await db.flush()
        print(f"   + {len(venue_rows)} venues")

        # ── Menu ─────────────────────────────────────────────────────────────
        menu_rows, venue_menu = [], {}
        for vm in venue_meta:
            items = []
            for m in MENU_BY_BRAND[vm["brand"]]:
                mid = uuid.uuid4()
                menu_rows.append({
                    "id": mid, "venue_id": vm["id"], "name": m["name"],
                    "category": m["cat"], "price": Decimal(str(m["price"])),
                    "description": None, "is_available": True,
                })
                items.append({"id": mid, "name": m["name"], "price": m["price"], "w": m["w"]})
            venue_menu[vm["id"]] = items
        await db.execute(insert(MenuItem), menu_rows)
        await db.flush()
        print(f"   + {len(menu_rows)} menu items")

        # ── Tables (bistros are table-service) ───────────────────────────────
        table_rows = []
        for vm in venue_meta:
            n_tables = 14 if vm["brand"] == "bistro" else 8
            for i in range(1, n_tables + 1):
                table_rows.append({
                    "id": uuid.uuid4(), "venue_id": vm["id"], "label": str(i),
                    "seats": random.choice([2, 2, 4, 4, 6]),
                    "status": "free", "created_at": now - timedelta(days=200),
                })
        await db.execute(insert(Table), table_rows)
        await db.flush()
        print(f"   + {len(table_rows)} tables")

        # ── Staff ────────────────────────────────────────────────────────────
        STAFF_ROLES = {
            "bistro": [("waiter", 4), ("senior_waiter", 2), ("manager", 1), ("bartender", 1)],
            "cafe":   [("barista", 3), ("waiter", 2), ("manager", 1)],
        }
        staff_rows, venue_staff = [], {}
        for vm in venue_meta:
            sids = []
            for role, count in STAFF_ROLES[vm["brand"]]:
                for _ in range(count):
                    sid = uuid.uuid4()
                    staff_rows.append({
                        "id": sid, "network_id": network.id, "venue_id": vm["id"],
                        "name": full_name(), "role": role, "is_active": True,
                        "avg_rating": None, "total_reviews": 0,
                        "created_at": now - timedelta(days=random.randint(40, 400)),
                    })
                    sids.append(sid)
            venue_staff[vm["id"]] = sids
        await db.execute(insert(Staff), staff_rows)
        await db.flush()
        print(f"   + {len(staff_rows)} staff")

        # ── Guests ───────────────────────────────────────────────────────────
        GUEST_COUNT = 450
        guest_ids, guest_rows = [], []
        for _ in range(GUEST_COUNT):
            gid = uuid.uuid4()
            guest_rows.append({
                "id": gid, "network_id": network.id, "name": full_name(),
                "phone": rand_phone(), "telegram_id": None,
                "total_points": 0, "total_visits": 0,
                "created_at": now - timedelta(days=random.randint(1, 400)),
            })
            guest_ids.append(gid)
        await db.execute(insert(Guest), guest_rows)
        await db.flush()
        print(f"   + {GUEST_COUNT} guests")

        # ── Orders: paid history + live today ────────────────────────────────
        PAY_METHODS = ["card"] * 55 + ["cash"] * 30 + ["mobile"] * 15
        LIVE_STATUSES = ["new", "new", "confirmed", "preparing", "preparing", "ready"]
        order_rows, item_rows, visit_rows = [], [], []
        guest_visits = {g: 0 for g in guest_ids}
        guest_points = {g: 0 for g in guest_ids}

        def build_lines(oid, items, weights):
            n_items = random.choices([1, 2, 3, 4, 5], weights=[18, 34, 28, 14, 6])[0]
            chosen = random.choices(items, weights=weights, k=n_items)
            seen = {}
            for mi in chosen:
                seen[mi["id"]] = seen.get(mi["id"], 0) + 1
            total = 0.0
            for mi_id, qty in seen.items():
                mi = next(x for x in items if x["id"] == mi_id)
                total += mi["price"] * qty
                item_rows.append({
                    "id": uuid.uuid4(), "order_id": oid, "menu_item_id": mi_id,
                    "name": mi["name"], "price": Decimal(str(mi["price"])), "quantity": qty,
                })
            return round(total, 2)

        for vm in venue_meta:
            items = venue_menu[vm["id"]]
            weights = [i["w"] for i in items]
            staff_names = [s["name"] for s in staff_rows if s["venue_id"] == vm["id"]]

            # Paid history
            for day in range(1, HIST_DAYS + 1):
                day_ts = now - timedelta(days=day)
                n = random.randint(vm["dmin"], vm["dmax"])
                if day_ts.weekday() >= 5:
                    n = int(n * 1.3)
                for _ in range(n):
                    oid = uuid.uuid4()
                    gid = random.choice(guest_ids)
                    total = build_lines(oid, items, weights)
                    hour = random.choices(
                        [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21],
                        weights=[3, 5, 6, 7, 12, 12, 8, 6, 6, 7, 10, 11, 8, 4],
                    )[0]
                    ts = day_ts.replace(hour=hour, minute=random.randint(0, 59),
                                        second=random.randint(0, 59), microsecond=0)
                    method = random.choice(PAY_METHODS)
                    # ~35% of card/mobile guests leave a tip; cash tips are rarer.
                    tip = Decimal("0")
                    if method in ("card", "mobile") and random.random() < 0.35:
                        tip = Decimal(str(round(total * random.choice([0.05, 0.07, 0.10, 0.10, 0.15]), 2)))
                    elif method == "cash" and random.random() < 0.12:
                        tip = Decimal(str(float(random.choice([1, 1, 2, 2, 5]))))
                    pts = int(total)
                    order_rows.append({
                        "id": oid, "venue_id": vm["id"], "guest_id": gid, "status": "done",
                        "total_amount": Decimal(str(total)), "subtotal_amount": None,
                        "tip_amount": tip, "points_earned": pts, "notes": None,
                        "payment_status": "paid", "payment_method": method, "paid_at": ts,
                        "source": "pos", "waiter_name": (random.choice(staff_names) if staff_names else None),
                        "created_at": ts, "updated_at": ts,
                    })
                    visit_rows.append({
                        "id": uuid.uuid4(), "guest_id": gid, "venue_id": vm["id"],
                        "order_id": oid, "visited_at": ts,
                    })
                    guest_visits[gid] += 1
                    guest_points[gid] += pts

            # Live today: in-progress (unpaid) + a couple served-awaiting-payment
            for _ in range(random.randint(6, 12)):
                oid = uuid.uuid4()
                gid = random.choice(guest_ids)
                total = build_lines(oid, items, weights)
                order_rows.append({
                    "id": oid, "venue_id": vm["id"], "guest_id": gid,
                    "status": random.choice(LIVE_STATUSES),
                    "total_amount": Decimal(str(total)), "subtotal_amount": None,
                    "tip_amount": Decimal("0"), "points_earned": 0, "notes": None,
                    "payment_status": "unpaid", "payment_method": None, "paid_at": None,
                    "source": "pos", "waiter_name": (random.choice(staff_names) if staff_names else None),
                    "created_at": now - timedelta(minutes=random.randint(2, 140)),
                    "updated_at": now - timedelta(minutes=random.randint(0, 10)),
                })

        BATCH = 2000
        print(f"   Inserting {len(order_rows):,} orders / {len(item_rows):,} lines...")
        for i in range(0, len(order_rows), BATCH):
            await db.execute(insert(Order), order_rows[i:i + BATCH])
        await db.flush()
        for i in range(0, len(item_rows), BATCH):
            await db.execute(insert(OrderItem), item_rows[i:i + BATCH])
        await db.flush()
        for i in range(0, len(visit_rows), BATCH):
            await db.execute(insert(Visit), visit_rows[i:i + BATCH])
        await db.flush()
        for gid in guest_ids:
            if guest_visits[gid]:
                await db.execute(sa.update(Guest).where(Guest.id == gid).values(
                    total_visits=guest_visits[gid], total_points=guest_points[gid]))
        await db.commit()

        paid_rev = sum(float(o["total_amount"]) for o in order_rows if o["status"] == "done")
        tips_total = sum(float(o["tip_amount"]) for o in order_rows)

        # ── Reviews (~35% of paid orders) ────────────────────────────────────
        review_rows = []
        s_sum, s_cnt = {}, {}
        done_by_venue = {}
        for o in order_rows:
            if o["status"] == "done":
                done_by_venue.setdefault(o["venue_id"], []).append(o)
        for vm in venue_meta:
            svc_ids = [s["id"] for s in staff_rows if s["venue_id"] == vm["id"]
                       and s["role"] in ("waiter", "senior_waiter", "barista")]
            if not svc_ids:
                continue
            for o in done_by_venue.get(vm["id"], []):
                if random.random() > 0.35:
                    continue
                overall = random.choices([5, 4, 4, 3, 2], weights=[42, 30, 14, 9, 5])[0]
                food_r = min(5, max(1, overall + random.randint(-1, 1)))
                svc_r = min(5, max(1, overall + random.randint(-1, 1)))
                sid = random.choice(svc_ids)
                if overall >= 4:
                    comment = random.choice(COMMENTS_POSITIVE) if random.random() < 0.6 else None
                elif overall == 3:
                    comment = random.choice(COMMENTS_NEUTRAL) if random.random() < 0.4 else None
                else:
                    comment = random.choice(COMMENTS_NEGATIVE) if random.random() < 0.5 else None
                review_rows.append({
                    "id": uuid.uuid4(), "venue_id": vm["id"], "order_id": o["id"],
                    "guest_id": o["guest_id"], "staff_id": sid, "food_rating": food_r,
                    "service_rating": svc_r, "overall_rating": overall, "comment": comment,
                    "source": "bot", "created_at": o["created_at"],
                })
                s_sum[sid] = s_sum.get(sid, 0.0) + overall
                s_cnt[sid] = s_cnt.get(sid, 0) + 1
        for i in range(0, len(review_rows), BATCH):
            await db.execute(insert(Review), review_rows[i:i + BATCH])
        for sid, cnt in s_cnt.items():
            await db.execute(sa.update(Staff).where(Staff.id == sid).values(
                avg_rating=round(s_sum[sid] / cnt, 2), total_reviews=cnt))
        await db.commit()
        print(f"   + {len(review_rows):,} reviews")

        # ── Inventory + write-offs ───────────────────────────────────────────
        KITCHEN = [
            ("Flour", "kg", 40, 10, 0.9), ("Sugar", "kg", 25, 5, 1.1),
            ("Butter", "kg", 12, 3, 8.5), ("Eggs", "pcs", 300, 60, 0.25),
            ("Milk", "l", 50, 12, 1.2), ("Cream", "l", 18, 4, 3.4),
            ("Parmesan", "kg", 8, 2, 22.0), ("Mozzarella", "kg", 15, 4, 9.0),
            ("Tomatoes", "kg", 20, 5, 2.8), ("Olive Oil", "l", 20, 5, 7.5),
            ("Pasta", "kg", 30, 8, 2.1), ("Ribeye Beef", "kg", 14, 3, 24.0),
            ("Coffee Beans", "kg", 18, 5, 16.0), ("Prosciutto", "kg", 6, 1.5, 28.0),
        ]
        CAFE_EXTRA = [
            ("Oat Milk", "l", 24, 6, 1.9), ("Almond Milk", "l", 12, 3, 2.2),
            ("Avocado", "pcs", 40, 12, 1.3), ("Sourdough Loaf", "pcs", 20, 6, 2.4),
            ("Matcha Powder", "kg", 1.2, 0.3, 90.0), ("Granola", "kg", 6, 1.5, 6.5),
        ]
        BAR = [
            ("Aperol", "l", 8, 2, 14.0), ("Prosecco", "l", 20, 5, 6.5),
            ("House Red Wine", "l", 24, 6, 5.0), ("Craft Lager keg", "l", 50, 10, 3.2),
            ("Gin", "l", 5, 1, 18.0), ("Tonic", "pcs", 60, 12, 0.8),
        ]
        ingredient_rows, writeoff_rows = [], []
        for vm in venue_meta:
            defs = [(n, u, q, m, c, "kitchen") for n, u, q, m, c in KITCHEN]
            if vm["brand"] == "cafe":
                defs += [(n, u, q, m, c, "kitchen") for n, u, q, m, c in CAFE_EXTRA]
            else:
                defs += [(n, u, q, m, c, "bar") for n, u, q, m, c in BAR]
            for name, unit, qty, min_q, cost, cat in defs:
                iid = uuid.uuid4()
                actual = round(qty * random.uniform(0.3, 1.6), 1)
                ingredient_rows.append({
                    "id": iid, "network_id": network.id, "venue_id": vm["id"],
                    "name": name, "unit": unit, "quantity": Decimal(str(actual)),
                    "min_quantity": Decimal(str(min_q)), "cost_per_unit": Decimal(str(cost)),
                    "category": cat, "created_at": now - timedelta(days=random.randint(30, 180)),
                })
                for _ in range(random.randint(1, 4)):
                    wo = round(random.uniform(0.3, max(0.4, actual * 0.3)), 2)
                    writeoff_rows.append({
                        "id": uuid.uuid4(), "ingredient_id": iid, "quantity": Decimal(str(wo)),
                        "reason": random.choice(["spoilage", "usage", "damage", "inventory"]),
                        "note": None, "created_by_id": None,
                        "created_at": now - timedelta(days=random.randint(1, 30)),
                    })
        await db.execute(insert(Ingredient), ingredient_rows)
        await db.execute(insert(WriteOff), writeoff_rows)
        await db.commit()
        print(f"   + {len(ingredient_rows)} inventory items, {len(writeoff_rows)} write-offs")

        # ── Expenses (6 months, EUR) ─────────────────────────────────────────
        TEMPLATES = {
            "bistro": [("rent", 4200, 5200), ("salaries", 11000, 14000),
                       ("ingredients", 6500, 8500), ("utilities", 900, 1500),
                       ("marketing", 500, 1200)],
            "cafe":   [("rent", 3200, 4000), ("salaries", 7000, 9500),
                       ("ingredients", 3800, 5200), ("utilities", 600, 1100),
                       ("marketing", 400, 900)],
        }
        ONE_OFF = [("equipment", 1500, 6000), ("other", 300, 1500)]
        expense_rows = []
        for vm in venue_meta:
            for months_back in range(6):
                m_date = today.replace(day=1)
                for _ in range(months_back):
                    m_date = (m_date - timedelta(days=1)).replace(day=1)
                for cat, lo, hi in TEMPLATES[vm["brand"]]:
                    d = m_date.replace(day=random.randint(1, 5) if cat in ("rent", "salaries")
                                       else random.randint(1, 28))
                    if d > today:
                        d = today
                    expense_rows.append({
                        "id": uuid.uuid4(), "network_id": network.id, "venue_id": vm["id"],
                        "category": cat, "amount": Decimal(str(random.randint(lo, hi))),
                        "description": None, "expense_date": d, "created_by_id": None,
                        "created_at": now - timedelta(days=months_back * 30 + random.randint(0, 5)),
                    })
            for _ in range(random.randint(1, 2)):
                cat, lo, hi = random.choice(ONE_OFF)
                d = today - timedelta(days=random.randint(0, 90))
                expense_rows.append({
                    "id": uuid.uuid4(), "network_id": network.id, "venue_id": vm["id"],
                    "category": cat, "amount": Decimal(str(random.randint(lo, hi))),
                    "description": None, "expense_date": d, "created_by_id": None,
                    "created_at": now - timedelta(days=random.randint(0, 90)),
                })
        await db.execute(insert(Expense), expense_rows)
        await db.commit()
        print(f"   + {len(expense_rows)} expense records")

        # ── Shifts (2 weeks back + this week + next) ─────────────────────────
        SHIFT_TIMES = {
            "bistro": [(time(10, 0), time(18, 0)), (time(16, 0), time(23, 30))],
            "cafe":   [(time(7, 0), time(15, 0)), (time(13, 0), time(20, 0))],
        }
        shift_rows = []
        week_monday0 = today - timedelta(days=today.weekday())
        for vm in venue_meta:
            sids = venue_staff[vm["id"]]
            times = SHIFT_TIMES[vm["brand"]]
            for wk in range(-2, 2):
                monday = week_monday0 + timedelta(weeks=wk)
                for d_off in range(7):
                    sday = monday + timedelta(days=d_off)
                    weekend = d_off >= 5
                    nm = random.randint(2, 4) if weekend else random.randint(1, 3)
                    ne = random.randint(2, 4) if weekend else random.randint(1, 3)
                    assigned = random.sample(sids, min(nm + ne, len(sids)))
                    status = "done" if sday < today else ("active" if sday == today else "planned")
                    for idx, sid in enumerate(assigned):
                        st, et = times[0] if idx < nm else times[1]
                        shift_rows.append({
                            "id": uuid.uuid4(), "staff_id": sid, "venue_id": vm["id"],
                            "shift_date": sday, "start_time": st, "end_time": et,
                            "status": status, "notes": None,
                            "created_at": now - timedelta(days=random.randint(0, 14)),
                        })
        await db.execute(insert(Shift), shift_rows)
        await db.commit()
        print(f"   + {len(shift_rows)} shifts")

        # ── Cash shifts (last 5 days closed + one open today per venue) ──────
        cash_rows = []
        for vm in venue_meta:
            for back in range(1, 6):
                opened = (now - timedelta(days=back)).replace(hour=8, minute=0, second=0, microsecond=0)
                closed = opened.replace(hour=22)
                cash_sales = Decimal(str(random.randint(400, 1400)))
                card_sales = Decimal(str(random.randint(900, 2600)))
                opening = Decimal("150.00")
                expected = opening + cash_sales
                diff = Decimal(str(round(random.uniform(-8, 6), 2)))
                cash_rows.append({
                    "id": uuid.uuid4(), "venue_id": vm["id"], "opened_by": DEMO_EMAIL,
                    "opening_cash": opening, "opened_at": opened,
                    "closed_by": DEMO_EMAIL, "closed_at": closed,
                    "closing_cash_actual": expected + diff, "notes": None,
                    "cash_sales": cash_sales, "card_sales": card_sales,
                    "orders_count": random.randint(40, 110),
                    "expected_cash": expected, "difference": diff,
                })
            # open shift for today
            cash_rows.append({
                "id": uuid.uuid4(), "venue_id": vm["id"], "opened_by": DEMO_EMAIL,
                "opening_cash": Decimal("150.00"),
                "opened_at": now.replace(hour=8, minute=0, second=0, microsecond=0),
                "closed_by": None, "closed_at": None, "closing_cash_actual": None,
                "notes": None, "cash_sales": None, "card_sales": None,
                "orders_count": None, "expected_cash": None, "difference": None,
            })
        await db.execute(insert(CashShift), cash_rows)
        await db.commit()
        print(f"   + {len(cash_rows)} cash shifts")

        print("\n✅ Done!")
        print(f"   Login:   {DEMO_EMAIL} / {DEMO_PASSWORD}")
        print(f"   Revenue ({HIST_DAYS}d): €{paid_rev:,.0f}  ·  tips €{tips_total:,.0f}")
        print(f"   Orders: {len(order_rows):,}  ·  guests: {GUEST_COUNT}  ·  reviews: {len(review_rows):,}")


if __name__ == "__main__":
    asyncio.run(main())
