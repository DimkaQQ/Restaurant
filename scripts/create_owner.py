"""
Creates the first owner account for a network.
Usage: python scripts/create_owner.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app.database import AsyncSessionLocal
from app.services.auth_service import register_network


async def main():
    print("=== RestOS — Создание владельца ===\n")

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        from app.models.network import Network
        from app.models.user import User
        from app.services.auth_service import hash_password

        networks = (await db.execute(select(Network))).scalars().all()
        if networks:
            print("Существующие сети:")
            for n in networks:
                print(f"  [{n.slug}] {n.name}  (ID: {n.id})")
            print()
            use_existing = input("Использовать существующую сеть? (y/n): ").strip().lower()
        else:
            use_existing = "n"

        if use_existing == "y":
            slug = input("Введи slug сети: ").strip()
            network = next((n for n in networks if n.slug == slug), None)
            if not network:
                print("❌ Сеть не найдена")
                return
        else:
            network_name = input("Название сети (например, &milk): ").strip()
            slug = input("Slug (например, andmilk): ").strip()
            from app.models.network import Network
            network = Network(name=network_name, slug=slug)
            db.add(network)
            await db.flush()

        email = input("Email владельца: ").strip()
        password = input("Пароль: ").strip()

        try:
            user = User(
                network_id=network.id,
                email=email,
                hashed_password=hash_password(password),
                role="owner",
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            print(f"\n✅ Готово!")
            print(f"   Сеть: {network.name} (slug: {network.slug})")
            print(f"   Пользователь: {email}")
            print(f"   User ID: {user.id}")
            print(f"   Network ID: {user.network_id}")
            print(f"\n   Сохрани Network ID — он нужен для бота (NETWORK_ID в .env)")
        except Exception as e:
            print(f"\n❌ Ошибка: {e}")


if __name__ == "__main__":
    asyncio.run(main())
