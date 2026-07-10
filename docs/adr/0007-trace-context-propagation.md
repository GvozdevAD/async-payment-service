# ADR 0007. Distributed tracing через сохранение контекста в payload

- Статус: Accepted
- Дата: 2026-07-10

## Контекст

Один бизнес-запрос проходит через асинхронные границы:
`POST /payments` → outbox (БД) → RabbitMQ → consumer → webhook_deliveries (БД) →
dispatcher → HTTP webhook. Между этапами есть «async gap»: запись лежит в БД, а
продолжает её уже другой процесс позже. Стандартная in-process propagation через
единый трейс здесь рвётся.

## Решение

W3C trace context (`traceparent`/`tracestate`) сериализуется и переносится через
границы (`app/core/propagation.py`):

- В outbox/webhook-payload кладётся ключ `trace_context` (`capture_trace_context`).
- В RabbitMQ контекст инжектится в заголовки сообщения (`inject_into_headers`),
  consumer восстанавливает родителя (`extract_context_from_headers`).
- Dispatcher поднимает span с родителем из payload (`context_from_carrier`).
- Перед отправкой наружу `strip_trace_context` **удаляет** внутренний ключ из
  тела вебхука — клиент его не видит.

## Альтернативы

- **Ничего не пробрасывать** — трейсы обрываются на каждой async-границе, теряется
  сквозная картина.
- **Только заголовки брокера** — не покрывает переходы через БД (outbox,
  webhook_deliveries), где «переносчик» — строка таблицы, а не сообщение.

## Последствия

- Сквозной трейс от HTTP-запроса до доставки вебхука.
- Payload немного растёт (несколько W3C-полей); внутренний ключ не протекает
  наружу благодаря `strip_trace_context`.
- Формат контекста завязан на W3C TraceContext propagator (осознанный стандартный выбор).
