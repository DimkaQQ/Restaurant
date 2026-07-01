.PHONY: help up down logs setup seed reseed bot reset test

# Цвета
GREEN  := \033[0;32m
YELLOW := \033[0;33m
NC     := \033[0m

help:
	@echo ""
	@echo "  $(GREEN)make up$(NC)     — запустить API + БД (миграции автоматом)"
	@echo "  $(GREEN)make bot$(NC)    — запустить бот + всё остальное"
	@echo "  $(GREEN)make setup$(NC)  — первый запуск: создать владельца сети"
	@echo "  $(GREEN)make seed$(NC)   — залить тестовые данные (заведения, меню, гости)"
	@echo "  $(GREEN)make reseed$(NC) — удалить и залить данные заново"
	@echo "  $(GREEN)make down$(NC)   — остановить всё"
	@echo "  $(GREEN)make logs$(NC)   — смотреть логи API"
	@echo "  $(GREEN)make reset$(NC)  — удалить БД и начать заново"
	@echo "  $(GREEN)make test$(NC)   — прогнать тесты (см. tests/README.md для первого запуска)"
	@echo ""

## Запуск API (БД + миграции + сервер)
up:
	@echo "$(GREEN)▶ Запускаем RestOS...$(NC)"
	docker compose up --build -d
	@echo ""
	@echo "$(GREEN)✓ Готово!$(NC)  Панель управления: http://restos.dimkaprojects.xyz"
	@echo "           Если первый раз — запусти: $(YELLOW)make setup$(NC)"

## Запуск вместе с ботом
bot:
	@echo "$(GREEN)▶ Запускаем RestOS + бот...$(NC)"
	docker compose --profile bot up --build -d
	@echo "$(GREEN)✓ Готово!$(NC)"

## Создать первого владельца (запускать после make up)
setup:
	docker compose exec api python scripts/create_owner.py

## Залить тестовые данные: заведения Chayla + меню + гости + заказы
seed:
	docker compose exec api python scripts/seed_data.py

## Удалить и залить данные заново
reseed:
	docker compose exec api python scripts/seed_data.py --force

## Логи
logs:
	docker compose logs -f api

logs-bot:
	docker compose logs -f bot

## Остановить
down:
	docker compose --profile bot down

## Сбросить БД полностью
reset:
	docker compose --profile bot down -v
	@echo "$(YELLOW)БД удалена.$(NC) Запусти: make up && make setup"

## Прогнать тесты против локального Postgres (см. tests/README.md)
test:
	python -m pytest tests/ -v
