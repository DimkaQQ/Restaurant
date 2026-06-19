# RestOS

SaaS-платформа для сетей ресторанов: Telegram-бот для гостей + веб-панель для управления.

## Стек

- **Backend**: Python 3.11, FastAPI, SQLAlchemy 2.0 (async), asyncpg
- **Database**: PostgreSQL 15
- **Bot**: aiogram 3.x
- **Templates**: Jinja2 + htmx
- **AI**: Anthropic Claude API

---

## Быстрый старт

### 1. Клонирование и настройка

```bash
cp .env.example .env
# Заполните .env своими значениями
```

### 2. Виртуальное окружение

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. База данных (через Docker)

```bash
docker compose up db -d
```

### 4. Миграции

```bash
alembic upgrade head
```

### 5. Создание первого владельца

```bash
python scripts/create_owner.py
```

Сохраните `Network ID` — он нужен для переменной `NETWORK_ID` в `.env`.

### 6. Запуск API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Панель управления: http://localhost:8000

### 7. Запуск бота

```bash
# В .env:
# BOT_TOKEN_VENUE_1=токен_из_BotFather
# NETWORK_ID=uuid_из_шага_5
# VENUE_ID_1=uuid_заведения

python -m bot.main
```

---

## Docker Compose (всё сразу)

```bash
cp .env.example .env
# Заполните .env
docker compose up --build
# Затем в отдельном окне:
docker compose exec api alembic upgrade head
docker compose exec api python scripts/create_owner.py
```

---

## Переменные окружения

| Переменная | Описание |
|---|---|
| `DATABASE_URL` | postgresql+asyncpg://user:pass@host/db |
| `SECRET_KEY` | JWT секрет (длинная случайная строка) |
| `ANTHROPIC_API_KEY` | Ключ Anthropic для AI-рекомендаций |
| `BOT_TOKEN_VENUE_1` | Токен Telegram-бота из BotFather |
| `NETWORK_ID` | UUID сети (получить из create_owner.py) |
| `VENUE_ID_1` | UUID заведения (создать через API) |
| `API_URL` | URL API для бота (default: http://localhost:8000) |

---

## Структура проекта

```
├── app/              # FastAPI приложение
│   ├── models/       # SQLAlchemy модели
│   ├── routers/      # API роутеры + HTML страницы
│   ├── services/     # Бизнес-логика
│   ├── templates/    # Jinja2 HTML
│   └── static/       # CSS/JS
├── bot/              # Telegram бот (aiogram 3)
├── migrations/       # Alembic миграции
└── scripts/          # Утилиты запуска
```

---

## Система баллов

- За каждые **1 000 ₸** заказа = **10 баллов**
- **100 баллов** = скидка **500 ₸**
- Баллы накапливаются во всех заведениях сети

## API эндпоинты

| Метод | URL | Описание |
|---|---|---|
| POST | `/auth/register` | Создать сеть + владельца |
| POST | `/auth/login` | Войти (access token + refresh cookie) |
| GET | `/api/venues/` | Список заведений |
| GET | `/api/menu/{venue_id}` | Меню заведения |
| POST | `/api/orders/?telegram_id=` | Создать заказ (из бота) |
| PATCH | `/api/orders/{id}/status` | Сменить статус заказа |
| GET | `/api/orders/live` | Активные заказы (для htmx polling) |
| GET | `/api/guests/` | Список гостей |
| GET | `/api/guests/{id}/recommendation` | AI-рекомендация для гостя |
