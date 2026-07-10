# Async Payment Processing Service

[![CI](https://github.com/GvozdevAD/async-payment-service/actions/workflows/ci.yml/badge.svg)](https://github.com/GvozdevAD/async-payment-service/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-0.2.0-blue)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![RabbitMQ](https://img.shields.io/badge/RabbitMQ-FF6600?logo=rabbitmq&logoColor=white)](https://www.rabbitmq.com/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-000000?logo=opentelemetry&logoColor=white)](https://opentelemetry.io/)

Микросервис асинхронной обработки платежей: API → Outbox → RabbitMQ → Consumer → Webhook.

История изменений: [CHANGELOG.md](CHANGELOG.md)

## Стек

- FastAPI + Pydantic v2
- SQLAlchemy 2.0 (async) + PostgreSQL
- RabbitMQ + FastStream
- Alembic, Docker Compose
- OpenTelemetry (traces + metrics via OTLP), Jaeger, Prometheus (local stack)

## Observability

При `OTEL_ENABLED=true` все процессы экспортируют **traces и metrics** через OTLP в `otel-collector`.

| Инструмент | URL (local compose) |
|------------|---------------------|
| Jaeger UI | http://localhost:16686 |
| Prometheus | http://localhost:9090 |

Сквозной distributed trace: `POST /payments` → outbox → RabbitMQ → consumer → webhook dispatcher → HTTP webhook.

Переменные окружения:

| Env | Default | Описание |
|-----|---------|----------|
| `OTEL_ENABLED` | `false` | Включить traces + metrics |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP gRPC endpoint |
| `OTEL_METRIC_EXPORT_INTERVAL_MS` | `10000` | Интервал экспорта метрик |

Локальный стек observability поднимается вместе с `docker compose -f docker-compose.yaml -f docker-compose.local.yaml up`.

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

## Безопасность вебхуков

`webhook_url` задаёт клиент, поэтому:

- **SSRF-защита** — URL проверяется при создании платежа (схема/порт/credentials) и повторно резолвится перед доставкой с блокировкой приватных адресов.
- **HMAC-подпись** — при заданном `WEBHOOK_SIGNING_SECRET` запросы подписываются HMAC-SHA256 (заголовки `X-Webhook-Signature`, `X-Webhook-Timestamp`).

Детали, альтернативы и trade-offs: [ADR 0008](docs/adr/0008-webhook-security-ssrf-hmac.md). Переменные — в `.env.example`.

## Retry и DLQ

| Этап | Попытки | Механизм |
|------|---------|----------|
| Outbox → RabbitMQ | 3 | tenacity, exponential backoff |
| Webhook HTTP | 3 | tenacity, exponential backoff |
| Consumer | 3 | `x-retry-count` header + nack/requeue → DLQ |

DLQ: очередь `payments.new.dlq` (см. `RABBITMQ_PAYMENTS_NEW_DLQ`).

## Trade-offs & Limitations

Границы системы проговорены явно — детали решений в [ADR](docs/adr/README.md).

### Delivery guarantees

- **At-least-once** на всех этапах: `outbox → RabbitMQ` (ADR [0001](docs/adr/0001-outbox-pattern.md)), `RabbitMQ → consumer` (ADR [0004](docs/adr/0004-dlq-retry-strategy.md)), `webhook_deliveries → HTTP` (ADR [0003](docs/adr/0003-webhook-delivery-outbox.md)). Exactly-once нет → **получатель вебхука обязан быть идемпотентным по `payment_id`**.
- **Дубли вебхуков** возможны при падении между успешным HTTP-ответом и `mark_delivered`: запись останется `PENDING` и будет доставлена повторно.
- **Порядок событий не гарантируется** — параллельная обработка и ретраи могут переставлять доставки.
- **Идемпотентность создания платежа** гарантируется UNIQUE-ключом + обработкой гонки `IntegrityError` (ADR [0005](docs/adr/0005-idempotency.md)).

### Scaling

- `publisher`, `consumer`, `webhook-dispatcher` — stateless и горизонтально масштабируются. Конкурентные поллеры безопасны за счёт `SELECT ... FOR UPDATE SKIP LOCKED`; повторный enqueue вебхука — за счёт `ON CONFLICT (payment_id) DO NOTHING`.
- Состояние живёт в БД: при рестарте процессов ничего не теряется — незавершённые записи подхватываются на следующем поллинге.

### Out of scope (сознательно)

Rate-limiting, ротация API-ключей, listing/пагинация платежей, exactly-once, архивация/очистка outbox, пин на резолвнутый IP для вебхуков.

### Known limitations

- **DNS-rebinding** между валидацией/резолвом и TCP-коннектом закрыт не полностью (ADR [0008](docs/adr/0008-webhook-security-ssrf-hmac.md)).
- **Requeue без задержки** на транзиентных ошибках consumer'а — попытки исчерпываются быстро (ADR [0004](docs/adr/0004-dlq-retry-strategy.md)).
- **Один вебхук на платёж** (`webhook_deliveries.payment_id` UNIQUE): повторная нотификация о том же платеже по дизайну не создаётся.

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

### Архитектурные решения (ADR)

*Почему* приняты ключевые решения — в [docs/adr/](docs/adr/README.md): Outbox
pattern, отдельные процессы publisher/dispatcher, DLQ-стратегия,
идемпотентность, observability, distributed tracing и безопасность вебхуков.
