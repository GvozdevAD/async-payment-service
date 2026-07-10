# Architecture Decision Records

Ключевые архитектурные решения и их обоснование. Формат — облегчённый MADR
(Status / Context / Decision / Alternatives / Consequences).

| ADR | Решение | Ключевой trade-off |
|-----|---------|--------------------|
| [0001](0001-outbox-pattern.md) | Outbox pattern для публикации событий | атомарность vs отдельный процесс-поллер |
| [0002](0002-separate-publisher-process.md) | Отдельный процесс `publisher` | масштабирование/изоляция vs простота |
| [0003](0003-webhook-delivery-outbox.md) | Второй транзакционный outbox для вебхуков | durability/декуплинг vs дублирование механизма |
| [0004](0004-dlq-retry-strategy.md) | DLQ через `x-retry-count` + nack/requeue | простота vs quorum queue + delivery-limit |
| [0005](0005-idempotency.md) | Идемпотентность: unique-key + обработка `IntegrityError` | корректность при конкуренции |
| [0006](0006-observability-otlp.md) | Единый OTLP-пайплайн, метрики только через OTel | единообразие vs привычный `/metrics` scrape |
| [0007](0007-trace-context-propagation.md) | Trace context в payload (async gap) | связность трейсов vs размер payload |
| [0008](0008-webhook-security-ssrf-hmac.md) | Безопасность вебхуков: SSRF + HMAC | безопасность vs доп. DNS-lookup и конфигурация |
