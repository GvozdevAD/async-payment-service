# Async Payment Processing Service

[![CI](https://github.com/GvozdevAD/async-payment-service/actions/workflows/ci.yml/badge.svg)](https://github.com/GvozdevAD/async-payment-service/actions/workflows/ci.yml)

Микросервис асинхронной обработки платежей: API → Outbox → RabbitMQ → Consumer → Webhook.

## Стек

- FastAPI + Pydantic v2
- SQLAlchemy 2.0 (async) + PostgreSQL
- RabbitMQ + FastStream
- Alembic, Docker Compose

## Makefile

Все команды проекта — через `make`. Справка по умолчанию:

```bash
make        # то же, что make help
make help
```

Вывод сгруппирован по блокам:

| Блок | Примеры |
|------|---------|
| General | `env`, `install` |
| PostgreSQL (pg) | `pg-up`, `pg-down`, `pg-logs` |
| API | `api-dev`, `api-prod`, `gen-openapi`, `smoke` |
| RabbitMQ (rabbit) | `rabbit-up`, `rabbit-down` |
| Consumer | `consumer-dev`, `consumer-up`, `nginx-up` |
| Database migrations (db) | `db-migrate`, `db-migrate-docker`, `db-revision` |
| Code quality | `lint`, `format`, `test`, `test-cov` |
| Full stack | `up`, `up-prod`, `down`, `logs` |

## Быстрый старт (local, API на хосте)

```bash
make env
make install
make pg-up && make rabbit-up
make db-migrate

# Терминал 1 — API (publisher встроен в lifespan)
make api-dev

# Терминал 2 — consumer
make consumer-dev

# Smoke-тест
make smoke
```

## Docker (полный стек)

```bash
make env
make up              # postgres → migrate → api, publisher, consumer

curl http://localhost:8000/api/v1/health
make smoke
```

Сервис `migrate` запускается автоматически при `make up` / `make up-prod` и выполняет `alembic upgrade head`. `api`, `publisher` и `consumer` стартуют только после успешного завершения миграций.

Повторно прогнать миграции (например, после `git pull` с новыми ревизиями):

```bash
make db-migrate-docker   # local
make db-migrate-prod     # prod
```

Prod (internal network + nginx):

```bash
make up-prod

curl http://localhost/api/v1/health
```

## Сервисы в Docker

| Сервис | Назначение |
|--------|------------|
| `postgres` | База данных |
| `rabbitmq` | Брокер сообщений |
| `migrate` | Alembic migrations (one-shot, автоматически при `up`) |
| `api` | HTTP API (gunicorn в production) |
| `publisher` | Публикация outbox → `payments.new` |
| `consumer` | Обработка платежей + webhook |
| `nginx` | Reverse proxy (только prod overlay) |

> **Почему `publisher` отдельно?** В production API (`APP_ENV=production`) outbox publisher в lifespan выключен — публикация идёт отдельным процессом. Это часть Outbox pattern.

## API

Спецификация: [docs/openapi.yaml](docs/openapi.yaml)

### Аутентификация

- `X-API-Key` — обязателен для `/api/v1/payments/*`
- `/api/v1/health` — **без ключа** (для Docker/K8s health probes)

### Примеры

```bash
export API_KEY=change-me-in-production
export IDEM_KEY="order-$(date +%s)"

# Health
curl -s http://localhost:8000/api/v1/health
curl -s http://localhost:8000/api/v1/health/ready

# Создать платёж
curl -s -X POST http://localhost:8000/api/v1/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -H "Idempotency-Key: $IDEM_KEY" \
  -d '{
    "amount": "100.50",
    "currency": "RUB",
    "description": "Test payment",
    "metadata": {"order_id": "1"},
    "webhook_url": "https://example.com/webhook"
  }'

# Получить платёж
curl -s -H "X-API-Key: $API_KEY" \
  http://localhost:8000/api/v1/payments/<payment_id>
```

Или: `make smoke`

## Retry и DLQ

| Этап | Попытки | Механизм |
|------|---------|----------|
| Outbox → RabbitMQ | 3 | tenacity, exponential backoff |
| Webhook HTTP | 3 | tenacity, exponential backoff |
| Consumer | 3 | `x-retry-count` header + nack/requeue → DLQ |

DLQ: очередь `payments.new.dlq` (см. `RABBITMQ_PAYMENTS_NEW_DLQ`).

## Переменные окружения

См. `.env.example`. Профиль `APP_ENV=local|production` задаётся в Makefile targets.

## Тесты

```bash
make pg-up && make db-migrate   # PostgreSQL нужен для integration-тестов
make test
make test-cov                   # 100% coverage по app/
make lint
```

## Архитектура

```
POST /payments → DB (payment + outbox)
                      ↓
              Outbox Publisher
                      ↓
              payments.new (RabbitMQ)
                      ↓
                 Consumer
           gateway (2-5s, 90%) → update status
                      ↓
              webhook (retry ×3)
```
