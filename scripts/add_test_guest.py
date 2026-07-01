"""
Add a test Telegram guest to the system.
Usage: python scripts/add_test_guest.py --tg-id 123456789 --name "Dimash"
"""
import asyncio
import argparse
import uuid
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.models.guest import Guest
from app.models.network import Network
from app.models.order import Order, OrderItem
from app.models.menu import MenuItem
from app.models.venue import Venue

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://restos:restos_secret@localhost/restos")


async def main(tg_id: int, name: str, lang: str):
    engine = create_async_engine(DATABASE_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        network = (await db.execute(select(Network))).scalars().first()
        if not network:
            print("❌ Сеть не найдена — сначала запусти seed_data.py")
            return

        # Upsert guest
        existing = (await db.execute(
            select(Guest).where(Guest.telegram_id == tg_id, Guest.network_id == network.id)
        )).scalar_one_or_none()

        if existing:
            print(f"ℹ️  Гость уже существует: {existing.name} (tg={tg_id})")
            guest = existing
        else:
            guest = Guest(
                id=uuid.uuid4(),
                network_id=network.id,
                telegram_id=tg_id,
                name=name,
                phone="+7 777 000 0000",
                total_points=350,
                total_visits=5,
                language=lang,
            )
            db.add(guest)
            await db.commit()
            await db.refresh(guest)
            print(f"✅ Гость создан: {guest.name} (id={guest.id})")

        # Get a venue and menu items to create sample orders
        venue = (await db.execute(
            select(Venue).where(Venue.network_id == network.id, Venue.is_active == True)
        )).scalars().first()

        if not venue:
            print("⚠️  Заведений нет, заказы не созданы")
            return

        # Check for existing orders
        existing_orders = (await db.execute(
            select(Order).where(Order.guest_id == guest.id)
        )).scalars().all()

        if existing_orders:
            print(f"ℹ️  У гостя уже {len(existing_orders)} заказов")
        else:
            items = (await db.execute(
                select(MenuItem).where(
                    MenuItem.venue_id == venue.id,
                    MenuItem.is_available == True,
                ).limit(6)
            )).scalars().all()

            if not items:
                print("⚠️  Позиций меню нет, заказы не созданы")
            else:
                from decimal import Decimal

                statuses = ["done", "done", "done", "done", "ready"]
                for i, status in enumerate(statuses):
                    picked = items[i % len(items): i % len(items) + 2] or items[:1]
                    total = sum(it.price for it in picked)
                    order = Order(
                        id=uuid.uuid4(),
                        venue_id=venue.id,
                        guest_id=guest.id,
                        status=status,
                        total_amount=total,
                        points_earned=int(total / 100),
                    )
                    db.add(order)
                    await db.flush()
                    for it in picked:
                        oi = OrderItem(
                            id=uuid.uuid4(),
                            order_id=order.id,
                            menu_item_id=it.id,
                            quantity=1,
                            price=it.price,
                            name=it.name,
                        )
                        db.add(oi)

                guest.total_visits = 5
                guest.total_points = 350
                await db.commit()
                print(f"✅ Создано {len(statuses)} тестовых заказов в заведении «{venue.name}»")

        print(f"\n📊 Итог:")
        print(f"   Имя: {guest.name}")
        print(f"   Telegram ID: {guest.telegram_id}")
        print(f"   Баллы: {guest.total_points}")
        print(f"   Язык: {guest.language}")
        print(f"   Заведение: {venue.name}")
        print(f"\nТеперь напиши /start боту — он тебя узнает!")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tg-id", type=int, required=True, help="Твой Telegram ID (числовой)")
    parser.add_argument("--name", default="Димаш", help="Имя в системе")
    parser.add_argument("--lang", default="ru", choices=["ru", "kz", "en"])
    args = parser.parse_args()
    asyncio.run(main(args.tg_id, args.name, args.lang))
