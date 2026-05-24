# Foreign Exchange Deal Manager

REST API для управления валютными сделками на Python с FastAPI, uv, Docker и Swagger.

## Структура проекта

```
fx-deal-manager/
├── src/fx_deal_manager/     # исходный код приложения
│   ├── api/                 # маршруты, JWT auth, dependencies
│   ├── core/                # конфигурация, БД, логирование
│   ├── domain/              # Pydantic-схемы
│   └── main.py              # точка входа FastAPI
├── scripts/                 # seed-demo-users.sh и др.
├── tests/
├── Dockerfile
├── docker-compose.yml       # API + PostgreSQL
├── docker-compose.dev.yml   # опционально: nginx + UI
├── pyproject.toml
└── uv.lock
```

## Требования

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker и Docker Compose
- [identity-provider](../identity-provider) — запускается отдельно (read-only)

## Порядок запуска (этап 0)

Три терминала — IdP не изменяем:

```bash
# 1. Identity Provider (:8083 — задайте SERVER_PORT=8083 в .env IdP)
cd ../identity-provider && docker compose up -d

# 2. FX Deal Manager API + PostgreSQL
cd fx-deal-manager
cp .env.example .env
docker compose up -d --build

# 3. UI (порт из CORS-allowlist IdP)
cd ../fx-deal-manager-ui
python3 -m http.server 5173
```

Альтернатива UI через nginx (прокси `/api` → :8000):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
# UI: http://localhost:5173
```

## Демо-пользователи

После запуска IdP создайте пользователей (вызывает API IdP, репозиторий не меняет):

```bash
chmod +x scripts/seed-demo-users.sh
./scripts/seed-demo-users.sh
```

| Email | Пароль | Роль |
|-------|--------|------|
| `trader@demo.local` | `DemoPassword1!` | TRADER |
| `positioner@demo.local` | `DemoPassword1!` | POSITIONER |
| `auditor@demo.local` | `DemoPassword1!` | AUDITOR |
| `admin@example.com` | `change-this-local-admin-password` | ADMIN (bootstrap IdP) |

## Проверка JWT (этап 0)

```bash
# Получить токен
TOKEN=$(curl -s http://localhost:8083/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"trader@demo.local","password":"DemoPassword1!"}' \
  | jq -r '.accessToken')

# Защищённый endpoint
curl -s http://localhost:8000/api/v1/me -H "Authorization: Bearer $TOKEN" | jq
```

В UI: войти на http://localhost:5173 — имя пользователя из JWT отображается в sidebar.

## Deal API (этап 1)

| Method | Path | Роль | Описание |
|--------|------|------|----------|
| POST | `/api/v1/deals` | TRADER | Создать сделку (статус DRAFT) |
| GET | `/api/v1/deals` | ALL | Реестр с фильтрами |
| GET | `/api/v1/deals/{id}` | ALL | Карточка сделки |
| PATCH | `/api/v1/deals/{id}` | TRADER | Редактирование (только DRAFT, только автор) |

Фильтры реестра: `status`, `deal_type`, `counterparty_id`, `trade_date_from`, `trade_date_to`, `search`, `page`, `page_size`.

```bash
TOKEN=$(curl -s http://localhost:8083/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"trader@demo.local","password":"DemoPassword1!"}' | jq -r '.accessToken')

curl -s http://localhost:8000/api/v1/deals \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "trade_date": "2026-05-08",
    "deal_type": "SPOT",
    "operation_direction": "BUY",
    "buy_currency": "USD",
    "sell_currency": "RUB",
    "amount": "750000.00",
    "rate": "92.4732",
    "counterparty_id": "VTBR"
  }' | jq
```

Миграции применяются автоматически при старте (`AUTO_MIGRATE=true`). Вручную: `make migrate`.

## Validate и NSI (этап 2)

| Method | Path | Роль | Описание |
|--------|------|------|----------|
| POST | `/api/v1/deals/{id}/validate` | TRADER | FLC + value date + 2 платежа + nostro |
| GET | `/api/v1/nsi/counterparties` | ALL | Справочник контрагентов |
| GET | `/api/v1/nsi/currencies` | ALL | Справочник валют |
| GET | `/api/v1/nsi/nostro-accounts` | ALL | Nostro-счета (`?currency_code=USD`) |

```bash
# Validate после создания сделки
curl -s -X POST http://localhost:8000/api/v1/deals/{id}/validate \
  -H "Authorization: Bearer $TOKEN" | jq

# Ошибка валидации → 422 с массивом {field, message}
```

## Workflow, аудит и интеграции (этапы 3–4)

| Method | Path | Роль | Описание |
|--------|------|------|----------|
| POST | `/api/v1/deals/{id}/submit` | TRADER | Отправка на согласование (после VALID) |
| POST | `/api/v1/deals/{id}/approve` | POSITIONER | Одобрение → position stub → `EXECUTED` |
| POST | `/api/v1/deals/{id}/return` | POSITIONER | Возврат с комментарием → `REJECTED` |
| POST | `/api/v1/deals/{id}/reject` | POSITIONER | Отклонение → `REJECTED` |
| POST | `/api/v1/deals/{id}/take-for-edit` | TRADER | `REJECTED` → `DRAFT` |
| GET | `/api/v1/deals/queue` | POSITIONER | Очередь согласования |
| GET | `/api/v1/audit-events` | ALL | Журнал аудита (`entity_id`, `user_id`, `from`, `to`) |
| POST | `/api/v1/nsi/sync` | ADMIN | Stub-синхронизация НСИ |

```bash
# Полный цикл до EXECUTED
curl -s -X POST .../deals/{id}/submit -H "Authorization: Bearer $TRADER_TOKEN"
curl -s -X POST .../deals/{id}/approve -H "Authorization: Bearer $POSITIONER_TOKEN" | jq

# Аудит по сделке
curl -s ".../audit-events?entity_id={id}" -H "Authorization: Bearer $TOKEN" | jq
```

## Локальная разработка (без Docker API)

```bash
uv sync --dev
cp .env.example .env
# PostgreSQL должен быть доступен на localhost:5433
docker compose up -d postgres
uv run uvicorn fx_deal_manager.main:app --reload
```

## Swagger / OpenAPI

| URL | Описание |
|-----|----------|
| `/docs` | Swagger UI |
| `/redoc` | ReDoc |
| `/openapi.json` | OpenAPI-схема |

## Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `DATABASE_URL` | `postgresql+asyncpg://fx:fx_password@localhost:5433/fx_deal_manager` | PostgreSQL |
| `JWT_ISSUER` | `http://localhost:8083` | Issuer JWT (IdP) |
| `JWKS_URL` | `http://localhost:8083/.well-known/jwks.json` | JWKS для валидации |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000` | Origins UI |
| `AUTO_MIGRATE` | `true` | Применять Alembic при старте |

## Тесты

```bash
uv run pytest
make test-integration   # PostgreSQL + RUN_INTEGRATION_TESTS=1
uv run ruff check src tests
```

## Docker

```bash
cp .env.example .env
docker compose up --build -d
# PostgreSQL: localhost:5433, API: localhost:8000
```
