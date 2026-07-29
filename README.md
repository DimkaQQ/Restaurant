# RestOS

SaaS-платформа для сетей ресторанов: касса, кухня, склад, финансы и white-label PWA для гостей.

## Стек

- **Backend**: Python 3.11, FastAPI, SQLAlchemy 2.0 (async), asyncpg
- **Database**: PostgreSQL 15
- **Guest app**: white-label PWA (QR-меню, установка на экран)
- **Templates**: Jinja2 + htmx
- **AI**: Anthropic Claude API

---

## Быстрый старт

```bash
cp .env.example .env   # заполните BOT_TOKEN_VENUE_1, ANTHROPIC_API_KEY
make up                # БД + миграции + API — всё автоматом
make setup             # создать первого владельца (один раз)
```

Панель управления: **http://localhost:8000**

### Остальные команды

```bash
make logs    # логи API
make down    # остановить всё
make reset   # сбросить БД и начать заново
make help    # список всех команд
```

---

## Переменные окружения

| Переменная | Описание |
|---|---|
| `DATABASE_URL` | postgresql+asyncpg://user:pass@host/db |
| `SECRET_KEY` | JWT секрет (длинная случайная строка) |
| `ANTHROPIC_API_KEY` | Ключ Anthropic для AI-рекомендаций |
| `PUBLIC_URL` | Публичный URL деплоя (для Stripe и cookie Secure/HSTS) |

---

## Структура проекта

```
├── app/              # FastAPI приложение
│   ├── models/       # SQLAlchemy модели
│   ├── routers/      # API роутеры + HTML страницы
│   ├── services/     # Бизнес-логика
│   ├── templates/    # Jinja2 HTML
│   └── static/       # CSS/JS
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
| POST | `/api/pos/order` | Создать заказ (касса) |
| PATCH | `/api/orders/{id}/status` | Сменить статус заказа |
| GET | `/api/orders/live` | Активные заказы (для htmx polling) |
| GET | `/api/guests/` | Список гостей |
| GET | `/api/guests/{id}/recommendation` | AI-рекомендация для гостя |
