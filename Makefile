.PHONY: help up down logs setup bot reset

# Цвета
GREEN  := \033[0;32m
YELLOW := \033[0;33m
NC     := \033[0m

help:
	@echo ""
	@echo "  $(GREEN)make up$(NC)     — запустить API + БД (миграции автоматом)"
	@echo "  $(GREEN)make bot$(NC)    — запустить бот + всё остальное"
	@echo "  $(GREEN)make setup$(NC)  — первый запуск: создать владельца сети"
	@echo "  $(GREEN)make down$(NC)   — остановить всё"
	@echo "  $(GREEN)make logs$(NC)   — смотреть логи API"
	@echo "  $(GREEN)make reset$(NC)  — удалить БД и начать заново"
	@echo ""

## Запуск API (БД + миграции + сервер)
up:
	@echo "$(GREEN)▶ Запускаем RestOS...$(NC)"
	docker compose up --build -d
	@echo ""
	@echo "$(GREEN)✓ Готово!$(NC)  Панель управления: http://localhost:8001"
	@echo "           Если первый раз — запусти: $(YELLOW)make setup$(NC)"

## Запуск вместе с ботом
bot:
	@echo "$(GREEN)▶ Запускаем RestOS + бот...$(NC)"
	docker compose --profile bot up --build -d
	@echo "$(GREEN)✓ Готово!$(NC)"

## Создать первого владельца (запускать после make up)
setup:
	docker compose exec api python scripts/create_owner.py

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
