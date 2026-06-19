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
    print("=== RestOS — Создание первого владельца ===\n")
    network_name = input("Название сети (например, &milk): ").strip()
    slug = input("Slug (например, andmilk): ").strip()
    email = input("Email владельца: ").strip()
    password = input("Пароль: ").strip()

    async with AsyncSessionLocal() as db:
        try:
            user = await register_network(network_name, slug, email, password, db)
            print(f"\n✅ Готово!")
            print(f"   Сеть: {network_name} (slug: {slug})")
            print(f"   Пользователь: {email}")
            print(f"   User ID: {user.id}")
            print(f"   Network ID: {user.network_id}")
            print(f"\n   Сохрани Network ID — он нужен для бота (NETWORK_ID в .env)")
        except Exception as e:
            print(f"\n❌ Ошибка: {e}")


if __name__ == "__main__":
    asyncio.run(main())
