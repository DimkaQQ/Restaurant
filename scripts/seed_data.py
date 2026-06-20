"""
Seed script: all Daniyar venues, full menus, 800 guests, 90 days of orders.
Uses bulk inserts — completes in ~15 seconds.

Usage:
  python scripts/seed_data.py           # skip if already seeded
  python scripts/seed_data.py --force   # wipe and re-seed
"""
import asyncio
import os
import sys
import uuid
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

import sqlalchemy as sa
from sqlalchemy import select, delete, insert

from app.database import AsyncSessionLocal
from app.models.network import Network
from app.models.venue import Venue
from app.models.menu import MenuItem
from app.models.guest import Guest
from app.models.order import Order, OrderItem, Visit
from app.models.points import PointsTransaction


# ── Venues ─────────────────────────────────────────────────────────────────────
VENUES = [
    # Chayla — чайхана
    {"brand": "Chayla", "name": "Chayla — Алмалы",    "address": "г. Алматы, ул. Жибек Жолы, 115",       "daily_min": 55, "daily_max": 95,  "avg_check": 4200},
    {"brand": "Chayla", "name": "Chayla — Достык",    "address": "г. Алматы, пр. Достык, 240",            "daily_min": 70, "daily_max": 130, "avg_check": 5100},
    {"brand": "Chayla", "name": "Chayla — Байзақов",  "address": "г. Алматы, ул. Байзақов, 280",          "daily_min": 40, "daily_max": 75,  "avg_check": 3900},
    {"brand": "Chayla", "name": "Chayla — Мега",      "address": "г. Алматы, ТРЦ Мега, Розы Багланова 7","daily_min": 80, "daily_max": 160, "avg_check": 4600},
    # &milk — milk bar / specialty coffee
    {"brand": "&milk", "name": "&milk — Esentai",     "address": "г. Алматы, пр. Аль-Фараби, 77/8",       "daily_min": 65, "daily_max": 120, "avg_check": 3400},
    {"brand": "&milk", "name": "&milk — Алмалы",      "address": "г. Алматы, ул. Панфилова, 98",          "daily_min": 50, "daily_max": 95,  "avg_check": 3200},
]

# ── Menus ───────────────────────────────────────────────────────────────────────
MENU_CHAYLA = [
    # Напитки
    {"name": "Чёрный чай (чайник)",         "category": "Напитки",        "price": 800},
    {"name": "Зелёный чай (чайник)",         "category": "Напитки",        "price": 800},
    {"name": "Чай с молоком",                "category": "Напитки",        "price": 900},
    {"name": "Шальчай",                      "category": "Напитки",        "price": 1000},
    {"name": "Чай с чабрецом и мёдом",       "category": "Напитки",        "price": 1100},
    {"name": "Матча латте",                  "category": "Напитки",        "price": 1500},
    {"name": "Капучино",                     "category": "Напитки",        "price": 1400},
    {"name": "Латте",                        "category": "Напитки",        "price": 1500},
    {"name": "Американо",                    "category": "Напитки",        "price": 1000},
    {"name": "Какао",                        "category": "Напитки",        "price": 1200},
    {"name": "Лимонад домашний",             "category": "Напитки",        "price": 1300},
    # Завтраки
    {"name": "Каша молочная",                "category": "Завтраки",       "price": 1200},
    {"name": "Яичница с овощами",            "category": "Завтраки",       "price": 1500},
    {"name": "Омлет с сыром",                "category": "Завтраки",       "price": 1600},
    {"name": "Авокадо тост",                 "category": "Завтраки",       "price": 2200},
    {"name": "Сырники со сметаной",          "category": "Завтраки",       "price": 1800},
    {"name": "Блинчики с мёдом",             "category": "Завтраки",       "price": 1700},
    # Выпечка
    {"name": "Самса с мясом",                "category": "Выпечка",        "price": 600},
    {"name": "Самса с тыквой",               "category": "Выпечка",        "price": 550},
    {"name": "Круассан масляный",            "category": "Выпечка",        "price": 900},
    {"name": "Круассан с шоколадом",         "category": "Выпечка",        "price": 1000},
    {"name": "Булочка с корицей",            "category": "Выпечка",        "price": 850},
    {"name": "Лепёшка тандырная",            "category": "Выпечка",        "price": 500},
    {"name": "Баурсаки",                     "category": "Выпечка",        "price": 700},
    # Горячие блюда
    {"name": "Лагман",                       "category": "Горячие блюда",  "price": 2800},
    {"name": "Манты (6 шт.)",               "category": "Горячие блюда",  "price": 2500},
    {"name": "Плов по-узбекски",             "category": "Горячие блюда",  "price": 2600},
    {"name": "Шурпа",                        "category": "Горячие блюда",  "price": 2400},
    {"name": "Бешбармак",                    "category": "Горячие блюда",  "price": 3500},
    {"name": "Самса-тандыр XXL",            "category": "Горячие блюда",  "price": 1200},
    # Десерты
    {"name": "Чизкейк классический",         "category": "Десерты",        "price": 1600},
    {"name": "Торт Наполеон (кусок)",        "category": "Десерты",        "price": 1400},
    {"name": "Медовик (кусок)",              "category": "Десерты",        "price": 1400},
    {"name": "Эклер шоколадный",             "category": "Десерты",        "price": 900},
    {"name": "Тирамису",                     "category": "Десерты",        "price": 1800},
    {"name": "Пахлава",                      "category": "Десерты",        "price": 800},
    {"name": "Мороженое (2 шарика)",         "category": "Десерты",        "price": 1000},
    {"name": "Шоколадный фондан",            "category": "Десерты",        "price": 1900},
]

MENU_MILK = [
    # Кофе
    {"name": "Эспрессо",                     "category": "Кофе",           "price": 900},
    {"name": "Американо",                    "category": "Кофе",           "price": 1000},
    {"name": "Капучино",                     "category": "Кофе",           "price": 1400},
    {"name": "Флэт Уайт",                    "category": "Кофе",           "price": 1500},
    {"name": "Кортадо",                      "category": "Кофе",           "price": 1500},
    {"name": "Латте",                        "category": "Кофе",           "price": 1500},
    {"name": "Раф кофе",                     "category": "Кофе",           "price": 1700},
    {"name": "Овсяный латте",                "category": "Кофе",           "price": 1800},
    # Напитки
    {"name": "Матча латте",                  "category": "Напитки",        "price": 1700},
    {"name": "Золотое молоко",               "category": "Напитки",        "price": 1500},
    {"name": "Смузи Клубника",               "category": "Напитки",        "price": 1800},
    {"name": "Смузи Манго-Авокадо",          "category": "Напитки",        "price": 1900},
    {"name": "Смузи Банан-Арахис",           "category": "Напитки",        "price": 1600},
    {"name": "Лимонад Базилик",              "category": "Напитки",        "price": 1300},
    # Еда
    {"name": "Авокадо тост с яйцом пашот",  "category": "Еда",            "price": 2500},
    {"name": "Клаб-сэндвич",                 "category": "Еда",            "price": 2800},
    {"name": "Боул с гранолой",              "category": "Еда",            "price": 2000},
    {"name": "Чиа-пудинг",                   "category": "Еда",            "price": 1400},
    {"name": "Салат Цезарь",                 "category": "Еда",            "price": 2400},
    {"name": "Яйца Бенедикт",               "category": "Еда",            "price": 2600},
    # Выпечка
    {"name": "Круассан масляный",            "category": "Выпечка",        "price": 900},
    {"name": "Круассан Ветчина & Сыр",       "category": "Выпечка",        "price": 1200},
    {"name": "Брауни",                       "category": "Выпечка",        "price": 1000},
    {"name": "Чизкейк",                      "category": "Выпечка",        "price": 1600},
    {"name": "Печенье (2 шт.)",              "category": "Выпечка",        "price": 700},
]

MENU_BY_BRAND = {"Chayla": MENU_CHAYLA, "&milk": MENU_MILK}

# ── 800 Guests ─────────────────────────────────────────────────────────────────
FIRST_NAMES = [
    "Алия", "Айгерим", "Динара", "Гульназ", "Зарина", "Камила", "Бота", "Сауле",
    "Нагима", "Аида", "Асель", "Жания", "Малика", "Ксения", "Ирина", "Анна",
    "Мария", "Наталья", "Екатерина", "Дарья", "Алина", "Юлия", "Кристина",
    "Марат", "Нурлан", "Руслан", "Ержан", "Асхат", "Тимур", "Данияр", "Бауыржан",
    "Ринат", "Алибек", "Сейткали", "Болат", "Санжар", "Максат", "Берик", "Талгат",
    "Олжас", "Аманжол", "Дулат", "Нурсултан", "Аскар", "Рустем", "Виктор",
    "Александр", "Сергей", "Дмитрий", "Андрей", "Иван", "Артём",
]
LAST_NAMES = [
    "Сейткали", "Джаксыбеков", "Ахметова", "Бейсенов", "Касымова", "Омаров",
    "Тулегенова", "Сагинтаев", "Абдрахманова", "Байжанов", "Сейтханова", "Мусаев",
    "Петрова", "Ким", "Досмагамбетова", "Жаксыбеков", "Нурмаганбетов",
    "Сулейменов", "Абенов", "Байдаулетов", "Ибрагимов", "Хасанов", "Назаров",
    "Каримов", "Рахимов", "Юсупов", "Матвеев", "Соколов", "Новиков", "Попов",
    "Лебедев", "Козлов", "Николаев", "Семёнов", "Голубев", "Виноградов",
    "Кузнецов", "Смирнов", "Иванов", "Васильев",
]

PHONE_PREFIXES = ["+7 701", "+7 702", "+7 705", "+7 707", "+7 747", "+7 771", "+7 777", "+7 778"]


def rand_phone() -> str:
    return f"{random.choice(PHONE_PREFIXES)} {random.randint(100,999)} {random.randint(1000,9999)}"


def rand_dt(days_back: float) -> datetime:
    delta = int(days_back * 86400)
    jitter = random.randint(0, 86400)
    return datetime.now(timezone.utc) - timedelta(seconds=delta * random.random() + jitter)


async def main():
    force = "--force" in sys.argv

    async with AsyncSessionLocal() as db:
        # Find network
        result = await db.execute(select(Network))
        network = result.scalars().first()
        if not network:
            print("❌ Нет сети. Сначала: make setup")
            return
        print(f"✅ Сеть: {network.name}")

        # Check existing
        existing = (await db.execute(
            select(Venue).where(Venue.network_id == network.id)
        )).scalars().first()

        if existing and not force:
            print("⚠️  Данные уже есть. Для перезаписи: make reseed")
            return

        if existing and force:
            print("   Очищаем старые данные...")
            await db.execute(delete(Visit).where(
                Visit.venue_id.in_(select(Venue.id).where(Venue.network_id == network.id))
            ))
            await db.execute(delete(PointsTransaction).where(
                PointsTransaction.network_id == network.id
            ))
            await db.execute(delete(OrderItem).where(
                OrderItem.order_id.in_(
                    select(Order.id).join(Venue).where(Venue.network_id == network.id)
                )
            ))
            await db.execute(delete(Order).where(
                Order.venue_id.in_(select(Venue.id).where(Venue.network_id == network.id))
            ))
            await db.execute(delete(MenuItem).where(
                MenuItem.venue_id.in_(select(Venue.id).where(Venue.network_id == network.id))
            ))
            await db.execute(delete(Guest).where(Guest.network_id == network.id))
            await db.execute(delete(Venue).where(Venue.network_id == network.id))
            await db.commit()

        # ── 1. Venues ───────────────────────────────────────────────────────────
        venue_rows = []
        venue_meta = []  # keep brand/daily info alongside id
        for v in VENUES:
            vid = uuid.uuid4()
            venue_rows.append({
                "id": vid,
                "network_id": network.id,
                "name": v["name"],
                "address": v["address"],
                "is_active": True,
                "created_at": datetime.now(timezone.utc) - timedelta(days=365),
            })
            venue_meta.append({**v, "id": vid})
        await db.execute(insert(Venue), venue_rows)
        await db.flush()
        print(f"   + {len(venue_rows)} заведений")

        # ── 2. Menu items ───────────────────────────────────────────────────────
        menu_rows = []
        venue_menu: dict[uuid.UUID, list[dict]] = {}
        for vm in venue_meta:
            items = []
            for m in MENU_BY_BRAND[vm["brand"]]:
                mid = uuid.uuid4()
                menu_rows.append({
                    "id": mid,
                    "venue_id": vm["id"],
                    "name": m["name"],
                    "category": m["category"],
                    "price": Decimal(str(m["price"])),
                    "description": None,
                    "is_available": True,
                })
                items.append({"id": mid, "name": m["name"], "price": m["price"]})
            venue_menu[vm["id"]] = items
        await db.execute(insert(MenuItem), menu_rows)
        await db.flush()
        print(f"   + {len(menu_rows)} позиций меню")

        # ── 3. Guests ────────────────────────────────────────────────────────────
        guest_count = 800
        guest_rows = []
        guest_ids = []
        for i in range(guest_count):
            gid = uuid.uuid4()
            guest_rows.append({
                "id": gid,
                "network_id": network.id,
                "name": f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
                "phone": rand_phone(),
                "telegram_id": None,
                "total_points": 0,
                "total_visits": 0,
                "created_at": datetime.now(timezone.utc) - timedelta(days=random.randint(1, 400)),
            })
            guest_ids.append(gid)
        await db.execute(insert(Guest), guest_rows)
        await db.flush()
        print(f"   + {guest_count} гостей")

        # ── 4. Orders (90 days history + live today) ─────────────────────────────
        STATUSES_HIST = ["done"] * 9 + ["cancelled"]
        STATUSES_LIVE = ["new", "new", "preparing", "preparing", "ready", "confirmed"]

        order_rows = []
        order_item_rows = []
        visit_rows = []
        guest_visits: dict[uuid.UUID, int] = {g: 0 for g in guest_ids}
        guest_points: dict[uuid.UUID, int] = {g: 0 for g in guest_ids}

        for vm in venue_meta:
            items = venue_menu[vm["id"]]

            # Historical: 90 days
            for day in range(1, 91):
                n = random.randint(vm["daily_min"], vm["daily_max"])
                # vary by day-of-week (weekends busier)
                day_ts = datetime.now(timezone.utc) - timedelta(days=day)
                weekday = day_ts.weekday()
                if weekday >= 5:
                    n = int(n * 1.3)

                for _ in range(n):
                    oid = uuid.uuid4()
                    gid = random.choice(guest_ids)
                    status = random.choice(STATUSES_HIST)
                    n_items = random.choices([1, 2, 3, 4], weights=[20, 40, 30, 10])[0]
                    chosen = random.sample(items, min(n_items, len(items)))

                    total = 0.0
                    for mi in chosen:
                        qty = random.randint(1, 3)
                        total += mi["price"] * qty
                        order_item_rows.append({
                            "id": uuid.uuid4(),
                            "order_id": oid,
                            "menu_item_id": mi["id"],
                            "name": mi["name"],
                            "price": Decimal(str(mi["price"])),
                            "quantity": qty,
                        })

                    order_dt = day_ts.replace(
                        hour=random.randint(9, 21),
                        minute=random.randint(0, 59),
                        second=0, microsecond=0
                    )
                    order_rows.append({
                        "id": oid,
                        "venue_id": vm["id"],
                        "guest_id": gid,
                        "status": status,
                        "total_amount": Decimal(str(round(total, 2))),
                        "points_earned": int(total // 1000) * 10 if status == "done" else 0,
                        "notes": None,
                        "created_at": order_dt,
                        "updated_at": order_dt,
                    })

                    if status == "done":
                        visit_rows.append({
                            "id": uuid.uuid4(),
                            "guest_id": gid,
                            "venue_id": vm["id"],
                            "order_id": oid,
                            "visited_at": order_dt,
                        })
                        guest_visits[gid] = guest_visits.get(gid, 0) + 1
                        guest_points[gid] = guest_points.get(gid, 0) + int(total // 1000) * 10

            # Live: today
            for _ in range(random.randint(vm["daily_min"] // 5, vm["daily_max"] // 5)):
                oid = uuid.uuid4()
                gid = random.choice(guest_ids)
                n_items = random.choices([1, 2, 3], weights=[30, 50, 20])[0]
                chosen = random.sample(items, min(n_items, len(items)))

                total = 0.0
                for mi in chosen:
                    qty = random.randint(1, 2)
                    total += mi["price"] * qty
                    order_item_rows.append({
                        "id": uuid.uuid4(),
                        "order_id": oid,
                        "menu_item_id": mi["id"],
                        "name": mi["name"],
                        "price": Decimal(str(mi["price"])),
                        "quantity": qty,
                    })

                now = datetime.now(timezone.utc)
                order_rows.append({
                    "id": oid,
                    "venue_id": vm["id"],
                    "guest_id": gid,
                    "status": random.choice(STATUSES_LIVE),
                    "total_amount": Decimal(str(round(total, 2))),
                    "points_earned": 0,
                    "notes": None,
                    "created_at": now - timedelta(minutes=random.randint(2, 90)),
                    "updated_at": now - timedelta(minutes=random.randint(0, 5)),
                })

        # Bulk insert orders in batches to avoid memory issues
        BATCH = 2000
        for i in range(0, len(order_rows), BATCH):
            await db.execute(insert(Order), order_rows[i:i+BATCH])
        await db.flush()

        for i in range(0, len(order_item_rows), BATCH):
            await db.execute(insert(OrderItem), order_item_rows[i:i+BATCH])
        await db.flush()

        for i in range(0, len(visit_rows), BATCH):
            await db.execute(insert(Visit), visit_rows[i:i+BATCH])
        await db.flush()

        # Update guest totals
        guest_update_rows = [
            {"id": gid, "total_visits": guest_visits[gid], "total_points": guest_points[gid]}
            for gid in guest_ids
            if guest_visits[gid] > 0
        ]
        for row in guest_update_rows:
            await db.execute(
                sa.update(Guest)
                .where(Guest.id == row["id"])
                .values(total_visits=row["total_visits"], total_points=row["total_points"])
            )

        await db.commit()

        total_orders = len(order_rows)
        live_orders = sum(1 for o in order_rows if o["status"] in ("new", "confirmed", "preparing", "ready"))
        print(f"   + {total_orders:,} заказов ({live_orders} активных сегодня)")
        print(f"   + {len(visit_rows):,} визитов")
        print(f"\n✅ Готово! Данные залиты.")


if __name__ == "__main__":
    asyncio.run(main())
