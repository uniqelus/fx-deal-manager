# Foreign Exchange Deal Manager

REST API для управления валютными сделками на Python с FastAPI, uv, Docker и Swagger.

## Структура проекта

```
fx-deal-manager/
├── src/fx_deal_manager/     # исходный код приложения
│   ├── api/routes/          # HTTP-маршруты
│   ├── core/                # конфигурация и общие модули
│   └── main.py              # точка входа FastAPI
├── tests/                   # тесты
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml           # зависимости и метаданные (uv)
└── uv.lock                  # lock-файл зависимостей
```

## Требования

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker и Docker Compose (опционально)

## Локальная разработка

```bash
# установка зависимостей
uv sync --dev

# копирование переменных окружения
cp .env.example .env

# запуск сервера
uv run fx-deal-manager
# или
uv run uvicorn fx_deal_manager.main:app --reload
```

API будет доступен на `http://localhost:8000`.

## Swagger / OpenAPI

| URL | Описание |
|-----|----------|
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/openapi.json` | OpenAPI-схема |

## Docker

```bash
cp .env.example .env
docker compose up --build
```

## Тесты

```bash
uv run pytest
uv run pytest --cov=fx_deal_manager
```

## Линтер

```bash
uv run ruff check src tests
uv run ruff format src tests
```
