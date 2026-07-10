# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-07-11

### Fixed

- Version test expected `0.1.0` while `pyproject.toml` declared `0.2.0`, breaking CI on `main`.

## [0.2.0] - 2026-07-11

### Added

- GitHub Actions CI: lint, tests, Docker build
- Webhook delivery outbox (`webhook_deliveries`) and separate `webhook-dispatcher` process
- Partial index on pending outbox rows to speed up polling
- OpenTelemetry: traces and metrics via OTLP; telemetry, metrics, and propagation modules
- Instrumentation across the full payment pipeline (API → outbox → RabbitMQ → consumer → webhook)
- Local observability stack: otel-collector, Jaeger, and Prometheus in Docker Compose
- SSRF protection for outbound webhooks (`url_guard`: scheme/port/credentials + DNS resolution)
- HMAC-SHA256 signing for outbound webhooks (`X-Webhook-Signature`, `X-Webhook-Timestamp`)
- Architecture Decision Records: `docs/adr/` (8 entries + index)
- README: webhook security, Trade-offs & Limitations, and ADR index sections
- Ruff: extended lint rule set in `pyproject.toml`

### Changed

- Global module state refactored into class-based singletons (`Database`, `Metrics`, `Observability`)
- Renamed `AppException` to `AppError` (PEP 8 naming, N818)
- Consumer enqueues webhooks via transactional outbox instead of direct HTTP delivery

### Security

- `webhook_url` validation at payment creation and re-check before delivery
- Block private, loopback, link-local, reserved, and multicast addresses (SSRF)
- HMAC payload signing when `WEBHOOK_SIGNING_SECRET` is configured

## [0.1.0] - 2026-07-10

### Added

- Async payment pipeline: API → transactional outbox → RabbitMQ → consumer
- Outbox publisher (separate process in production; embedded in API lifespan for local)
- Payment consumer with gateway emulation and DLQ via `x-retry-count`
- Idempotent `POST /payments` via `Idempotency-Key` (UNIQUE constraint + race handling)
- Webhook enqueue from consumer (no separate dispatcher yet)
- Docker Compose, Makefile, Alembic migrations, smoke test
- 100% test coverage, RFC 7807 error responses, API key authentication
- README and OpenAPI spec (`docs/openapi.yaml`)

[unreleased]: https://github.com/GvozdevAD/async-payment-service/compare/0.2.1...HEAD
[0.2.1]: https://github.com/GvozdevAD/async-payment-service/compare/0.2.0...0.2.1
[0.2.0]: https://github.com/GvozdevAD/async-payment-service/compare/0.1.0...0.2.0
[0.1.0]: https://github.com/GvozdevAD/async-payment-service/releases/tag/0.1.0
[SemVer]: https://semver.org/spec/v2.0.0.html
