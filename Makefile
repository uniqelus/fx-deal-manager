.DEFAULT_GOAL := help

UV := uv
COMPOSE := docker compose

SRC := src tests

.PHONY: help install env run dev test test-cov lint format fmt check docker-build docker-up docker-down docker-logs clean

help: ## Показать доступные команды
	@grep -E '^[a-zA-Z0-9_-]+:.*##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Установить зависимости (uv sync --dev)
	$(UV) sync --dev

env: ## Создать .env из .env.example
	@test -f .env || cp .env.example .env
	@echo ".env готов"

run: ## Запустить API
	$(UV) run fx-deal-manager

dev: ## Запустить API с hot-reload
	$(UV) run uvicorn fx_deal_manager.main:app --reload --host 0.0.0.0 --port 8000

test: ## Запустить тесты
	$(UV) run pytest

test-cov: ## Тесты с покрытием
	$(UV) run pytest --cov=fx_deal_manager --cov-report=term-missing

lint: ## Проверить код (ruff)
	$(UV) run ruff check $(SRC)

format: ## Отформатировать код (ruff)
	$(UV) run ruff format $(SRC)

fmt: format ## Алиас для format

check: lint test ## Линтер + тесты

docker-build: ## Собрать Docker-образ
	$(COMPOSE) build

docker-up: env ## Запустить контейнеры
	$(COMPOSE) up --build -d

docker-down: ## Остановить контейнеры
	$(COMPOSE) down

docker-logs: ## Логи контейнеров
	$(COMPOSE) logs -f

clean: ## Удалить кэш и артефакты сборки
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
