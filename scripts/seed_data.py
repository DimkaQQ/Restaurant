"""
Seed script: adds Chayla venues, full menu, test guests and orders.
Usage: python scripts/seed_data.py
"""
import asyncio
import os
import sys
import uuid
import random
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.network import Network
from app.models.venue import Venue
from app.models.menu import MenuItem
from app.models.guest import Guest
from app.models.order import Order, OrderItem, Visit
from app.models.points import PointsTransaction


VENUES = [
    {
        "name": "Chayla — Арбат",
        "address": "г. Алматы, ул. Арбат, 15",
    },
    {
        "name": "Chayla — Достык",
        "address": "г. Алматы, пр. Достык, 97",
    },
]

MENU = [
    # ─── Чай & Кофе ────────────────────────────────────────────────────────────
    {"name": "Чёрный чай (чайник)", "category": "Напитки", "price": 800, "description": "Крупнолистовой цейлонский чай, чайник 500 мл"},
    {"name": "Зелёный чай (чайник)", "category": "Напитки", "price": 800, "description": "Китайский зелёный чай, чайник 500 мл"},
    {"name": "Чай с молоком", "category": "Напитки", "price": 900, "description": "Крепкий чай с топлёным молоком"},
    {"name": "Шальчай", "category": "Напитки", "price": 1000, "description": "Традиционный казахский чай с молоком и солью"},
    {"name": "Чай с чабрецом и мёдом", "category": "Напитки", "price": 1100, "description": "Травяной чай с горным мёдом"},
    {"name": "Матча латте", "category": "Напитки", "price": 1500, "description": "Японский чай матча с молоком"},
    {"name": "Капучино", "category": "Напитки", "price": 1400, "description": "Двойной эспрессо с молочной пенкой"},
    {"name": "Латте", "category": "Напитки", "price": 1500, "description": "Мягкий кофе с большим количеством молока"},
    {"name": "Американо", "category": "Напитки", "price": 1000, "description": "Классический чёрный кофе"},
    {"name": "Какао", "category": "Напитки", "price": 1200, "description": "Горячий какао на молоке"},
    {"name": "Лимонад домашний", "category": "Напитки", "price": 1300, "description": "Сезонный лимонад, 400 мл"},

    # ─── Завтраки ───────────────────────────────────────────────────────────────
    {"name": "Каша молочная", "category": "Завтраки", "price": 1200, "description": "Овсяная каша на молоке с ягодами"},
    {"name": "Яичница с овощами", "category": "Завтраки", "price": 1500, "description": "Три яйца, болгарский перец, помидор"},
    {"name": "Омлет с сыром", "category": "Завтраки", "price": 1600, "description": "Пышный омлет с сыром Гауда"},
    {"name": "Авокадо тост", "category": "Завтраки", "price": 2200, "description": "Хлеб на закваске, авокадо, яйцо пашот"},
    {"name": "Сырники со сметаной", "category": "Завтраки", "price": 1800, "description": "Домашние сырники с джемом и сметаной"},
    {"name": "Блинчики с мёдом", "category": "Завтраки", "price": 1700, "description": "5 тонких блинчиков с маслом и мёдом"},

    # ─── Выпечка ────────────────────────────────────────────────────────────────
    {"name": "Самса с мясом", "category": "Выпечка", "price": 600, "description": "Слоёная самса с говядиной и луком"},
    {"name": "Самса с тыквой", "category": "Выпечка", "price": 550, "description": "Слоёная самса с тыквой"},
    {"name": "Круассан масляный", "category": "Выпечка", "price": 900, "description": "Классический французский круассан"},
    {"name": "Круассан с шоколадом", "category": "Выпечка", "price": 1000, "description": "Круассан с ганашем из тёмного шоколада"},
    {"name": "Булочка с корицей", "category": "Выпечка", "price": 850, "description": "Мягкая булочка с корицей и глазурью"},
    {"name": "Лепёшка тандырная", "category": "Выпечка", "price": 500, "description": "Свежая лепёшка из тандыра"},
    {"name": "Баурсаки", "category": "Выпечка", "price": 700, "description": "Традиционные казахские пончики, 6 шт."},

    # ─── Горячие блюда ──────────────────────────────────────────────────────────
    {"name": "Лагман", "category": "Горячие блюда", "price": 2800, "description": "Узбекский лагман с говядиной и овощами"},
    {"name": "Манты (6 шт.)", "category": "Горячие блюда", "price": 2500, "description": "Паровые манты с говядиной и луком"},
    {"name": "Плов по-узбекски", "category": "Горячие блюда", "price": 2600, "description": "Рис с бараниной, морковью и специями"},
    {"name": "Шурпа", "category": "Горячие блюда", "price": 2400, "description": "Наваристый суп с бараниной"},
    {"name": "Бешбармак", "category": "Горячие блюда", "price": 3500, "description": "Традиционное казахское блюдо с говядиной"},

    # ─── Десерты ────────────────────────────────────────────────────────────────
    {"name": "Чизкейк классический", "category": "Десерты", "price": 1600, "description": "Нью-Йорк чизкейк с ягодным соусом"},
    {"name": "Торт Наполеон (кусок)", "category": "Десерты", "price": 1400, "description": "Классический Наполеон с кремом"},
    {"name": "Медовик (кусок)", "category": "Десерты", "price": 1400, "description": "Медовый торт со сметанным кремом"},
    {"name": "Эклер шоколадный", "category": "Десерты", "price": 900, "description": "Заварной эклер с шоколадной глазурью"},
    {"name": "Тирамису", "category": "Десерты", "price": 1800, "description": "Классический итальянский десерт"},
    {"name": "Пахлава", "category": "Десерты", "price": 800, "description": "Восточная сладость с орехами и мёдом, 3 шт."},
    {"name": "Мороженое (2 шарика)", "category": "Десерты", "price": 1000, "description": "Ванильное или шоколадное мороженое"},
]

GUESTS = [
    {"name": "Алия Сейткали", "phone": "+7 701 234 5678"},
    {"name": "Марат Джаксыбеков", "phone": "+7 702 345 6789"},
    {"name": "Динара Ахметова", "phone": "+7 707 456 7890"},
    {"name": "Нурлан Бейсенов", "phone": "+7 747 567 8901"},
    {"name": "Айгерим Касымова", "phone": "+7 771 678 9012"},
    {"name": "Руслан Омаров", "phone": "+7 777 789 0123"},
    {"name": "Зарина Тулегенова", "phone": "+7 701 890 1234"},
    {"name": "Ержан Сагинтаев", "phone": "+7 702 901 2345"},
    {"name": "Камила Абдрахманова", "phone": "+7 705 012 3456"},
    {"name": "Тимур Байжанов", "phone": "+7 778 123 4567"},
    {"name": "Гульназ Сейтханова", "phone": "+7 771 234 5670"},
    {"name": "Асхат Мусаев", "phone": "+7 747 345 6781"},
    {"name": "Инна Петрова", "phone": "+7 702 456 7892"},
    {"name": "Владимир Ким", "phone": "+7 701 567 8903"},
    {"name": "Бота Досмагамбетова", "phone": "+7 777 678 9014"},
]


def rand_dt(days_back_min: int, days_back_max: int) -> datetime:
    delta = random.randint(days_back_min * 86400, days_back_max * 86400)
    return datetime.now(timezone.utc) - timedelta(seconds=delta)


async def main():
    async with AsyncSessionLocal() as db:
        # Find the network
        result = await db.execute(select(Network))
        network = result.scalars().first()
        if not network:
            print("❌ Нет ни одной сети. Сначала запусти: make setup")
            return

        print(f"✅ Сеть: {network.name} (id={network.id})")

        # Check if already seeded
        existing = await db.execute(select(Venue).where(Venue.network_id == network.id))
        if existing.scalars().first():
            print("⚠️  Данные уже есть. Пропускаем.")
            return

        # ── Venues ──────────────────────────────────────────────────────────────
        venues = []
        for v_data in VENUES:
            venue = Venue(
                id=uuid.uuid4(),
                network_id=network.id,
                name=v_data["name"],
                address=v_data["address"],
                is_active=True,
            )
            db.add(venue)
            venues.append(venue)
        await db.flush()
        print(f"   + {len(venues)} заведений")

        # ── Menu items (same menu for both venues) ───────────────────────────────
        all_items = []
        for venue in venues:
            for m in MENU:
                item = MenuItem(
                    id=uuid.uuid4(),
                    venue_id=venue.id,
                    name=m["name"],
                    category=m["category"],
                    price=m["price"],
                    description=m["description"],
                    is_available=True,
                )
                db.add(item)
                all_items.append(item)
        await db.flush()
        print(f"   + {len(all_items)} позиций меню")

        # ── Guests ───────────────────────────────────────────────────────────────
        guests = []
        for g_data in GUESTS:
            guest = Guest(
                id=uuid.uuid4(),
                network_id=network.id,
                name=g_data["name"],
                phone=g_data["phone"],
                total_points=0,
                total_visits=0,
                created_at=rand_dt(60, 180),
            )
            db.add(guest)
            guests.append(guest)
        await db.flush()
        print(f"   + {len(guests)} гостей")

        # ── Orders ───────────────────────────────────────────────────────────────
        statuses_hist = ["done"] * 8 + ["cancelled"]
        statuses_live = ["new", "preparing", "ready"]
        orders_added = 0

        for venue in venues:
            venue_items = [i for i in all_items if i.venue_id == venue.id]

            # Historical orders (last 90 days)
            for _ in range(80):
                guest = random.choice(guests)
                n_items = random.randint(1, 4)
                chosen = random.sample(venue_items, min(n_items, len(venue_items)))
                created = rand_dt(1, 90)

                order = Order(
                    id=uuid.uuid4(),
                    venue_id=venue.id,
                    guest_id=guest.id,
                    status=random.choice(statuses_hist),
                    created_at=created,
                    updated_at=created,
                )
                db.add(order)
                await db.flush()

                total = 0
                for mi in chosen:
                    qty = random.randint(1, 3)
                    oi = OrderItem(
                        id=uuid.uuid4(),
                        order_id=order.id,
                        menu_item_id=mi.id,
                        name=mi.name,
                        price=mi.price,
                        quantity=qty,
                    )
                    db.add(oi)
                    total += float(mi.price) * qty

                order.total_amount = round(total, 2)
                order.points_earned = int(total // 1000) * 10

                if order.status == "done":
                    visit = Visit(
                        id=uuid.uuid4(),
                        guest_id=guest.id,
                        venue_id=venue.id,
                        order_id=order.id,
                        visited_at=created,
                    )
                    db.add(visit)
                    guest.total_visits += 1
                    guest.total_points += order.points_earned

                orders_added += 1

            # Live orders (today)
            for _ in range(random.randint(3, 6)):
                guest = random.choice(guests)
                n_items = random.randint(1, 3)
                chosen = random.sample(venue_items, min(n_items, len(venue_items)))
                created = rand_dt(0, 0)

                order = Order(
                    id=uuid.uuid4(),
                    venue_id=venue.id,
                    guest_id=guest.id,
                    status=random.choice(statuses_live),
                    created_at=created,
                    updated_at=created,
                )
                db.add(order)
                await db.flush()

                total = 0
                for mi in chosen:
                    qty = random.randint(1, 2)
                    oi = OrderItem(
                        id=uuid.uuid4(),
                        order_id=order.id,
                        menu_item_id=mi.id,
                        name=mi.name,
                        price=mi.price,
                        quantity=qty,
                    )
                    db.add(oi)
                    total += float(mi.price) * qty

                order.total_amount = round(total, 2)
                orders_added += 1

        await db.commit()
        print(f"   + {orders_added} заказов")
        print("\n✅ Тестовые данные добавлены!")


if __name__ == "__main__":
    asyncio.run(main())
