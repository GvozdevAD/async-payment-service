# syntax=docker/dockerfile:1

FROM python:3.14-slim-bookworm AS builder

WORKDIR /app

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PIP_NO_CACHE_DIR=1

RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-ansi --only migration --no-root

FROM python:3.14-slim-bookworm AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

ENTRYPOINT ["python", "-m", "alembic"]
CMD ["upgrade", "head"]
