.DEFAULT_GOAL := help

# Help convention:
#   # @section Block name  — group header in `make help`
#   target: [deps] ## Description — appears under the current section

PROJECT_NAME     ?= test-task
COMPOSE_FILE_BASE  := docker-compose.yaml
COMPOSE_FILE_LOCAL := docker-compose.local.yaml
COMPOSE_FILE_PROD  := docker-compose.prod.yaml
COMPOSE_LOCAL := docker compose -p $(PROJECT_NAME) \
	-f $(COMPOSE_FILE_BASE) -f $(COMPOSE_FILE_LOCAL)
COMPOSE_PROD := docker compose -p $(PROJECT_NAME) \
	-f $(COMPOSE_FILE_BASE) -f $(COMPOSE_FILE_PROD)
COMPOSE          := $(COMPOSE_LOCAL)
PG_SERVICE       := postgres
API_SERVICE      := api
RABBIT_SERVICE   := rabbitmq
PUBLISHER_SERVICE := publisher
MIGRATE_SERVICE  := migrate
CONSUMER_SERVICE := consumer
NGINX_SERVICE    := nginx

APP_ENV_LOCAL      := local
APP_ENV_PRODUCTION := production

API_HOST         ?= 0.0.0.0
API_PORT         ?= 8000
POETRY_RUN       := poetry run
UVICORN          := $(POETRY_RUN) uvicorn app.main:app
GUNICORN         := $(POETRY_RUN) gunicorn

# ------------------------------------------------------------------------------
# Colors
# ------------------------------------------------------------------------------

RESET   := \033[0m
BOLD    := \033[1m
DIM     := \033[2m
RED     := \033[0;31m
GREEN   := \033[0;32m
YELLOW  := \033[0;33m
BLUE    := \033[0;34m
MAGENTA := \033[0;35m
CYAN    := \033[0;36m
WHITE   := \033[0;37m

COLOR_TITLE   := $(BOLD)$(BLUE)
COLOR_SECTION := $(BOLD)$(CYAN)
COLOR_TARGET  := $(GREEN)
COLOR_DESC    := $(DIM)$(WHITE)
COLOR_USAGE   := $(BOLD)$(YELLOW)

# ------------------------------------------------------------------------------
# @section General
# ------------------------------------------------------------------------------

.PHONY: help env install
help: ## Show available commands grouped by block
	@printf "\n"
	@printf "$(COLOR_TITLE)%s$(RESET) — available commands\n\n" "$(PROJECT_NAME)"
	@printf "$(COLOR_USAGE)Usage:$(RESET) make $(COLOR_TARGET)<target>$(RESET)\n"
	@awk 'BEGIN {FS = ":.*##"} \
		/^# @section / { gsub(/^# @section /, ""); printf "\n$(COLOR_SECTION)%s$(RESET)\n", $$0; next } \
		/^[a-zA-Z0-9_-]+:.*##/ { printf "  $(COLOR_TARGET)%-18s$(RESET)$(COLOR_DESC)%s$(RESET)\n", $$1, $$2 }' \
		$(MAKEFILE_LIST)
	@printf "\n"

env: ## Create .env from .env.example if missing
	@test -f .env || cp .env.example .env
	@echo ".env is ready"

install: ## Install project dependencies via Poetry
	poetry install --with migration

# ------------------------------------------------------------------------------
# @section PostgreSQL (pg)
# ------------------------------------------------------------------------------

.PHONY: pg-up pg-down pg-down-v pg-restart pg-logs pg-ps
pg-up: env ## Start PostgreSQL container
	$(COMPOSE) up -d $(PG_SERVICE)

pg-down: ## Stop PostgreSQL container
	$(COMPOSE) stop $(PG_SERVICE)

pg-down-v: ## Stop PostgreSQL and remove data volume
	$(COMPOSE) stop $(PG_SERVICE)
	-$(COMPOSE) rm -f $(PG_SERVICE)
	-docker volume rm $(PROJECT_NAME)_postgres_data 2>/dev/null || true

pg-restart: ## Restart PostgreSQL container
	$(COMPOSE) restart $(PG_SERVICE)

pg-logs: ## Tail PostgreSQL logs
	$(COMPOSE) logs -f $(PG_SERVICE)

pg-ps: ## Show PostgreSQL container status
	$(COMPOSE) ps $(PG_SERVICE)

# ------------------------------------------------------------------------------
# @section API
# ------------------------------------------------------------------------------

.PHONY: api-dev api-prod api-up api-down api-restart api-build api-logs gen-openapi
api-dev: env ## Run API locally with hot reload (local profile)
	APP_ENV=$(APP_ENV_LOCAL) $(UVICORN) --reload --host $(API_HOST) --port $(API_PORT)

api-prod: env ## Run API with Gunicorn (production profile)
	APP_ENV=$(APP_ENV_PRODUCTION) $(GUNICORN) -c gunicorn.conf.py app.main:app

api-up: env ## Start API container (production)
	$(COMPOSE) up -d $(API_SERVICE)

api-down: ## Stop API container
	$(COMPOSE) stop $(API_SERVICE)

api-restart: ## Restart API container
	$(COMPOSE) restart $(API_SERVICE)

api-build: ## Build API Docker image
	$(COMPOSE) build $(API_SERVICE)

api-logs: ## Tail API container logs
	$(COMPOSE) logs -f $(API_SERVICE)

gen-openapi: ## Generate OpenAPI schema to docs/openapi.yaml
	PYTHONPATH=. $(POETRY_RUN) python scripts/generate_openapi.py

smoke: env ## Run API smoke tests (auto-detect :8000 or nginx :80)
	./scripts/smoke.sh

.PHONY: publisher-dev publisher-prod publisher-up publisher-down publisher-restart publisher-build publisher-logs
publisher-dev: env ## Run outbox publisher locally (local profile)
	APP_ENV=$(APP_ENV_LOCAL) $(POETRY_RUN) python -m app.publisher.main

publisher-prod: env ## Run outbox publisher locally (production profile)
	APP_ENV=$(APP_ENV_PRODUCTION) $(POETRY_RUN) python -m app.publisher.main

publisher-up: env ## Start publisher container (local compose)
	$(COMPOSE_LOCAL) up -d $(PUBLISHER_SERVICE)

publisher-down: ## Stop publisher container
	$(COMPOSE_LOCAL) stop $(PUBLISHER_SERVICE)

publisher-restart: ## Restart publisher container
	$(COMPOSE_LOCAL) restart $(PUBLISHER_SERVICE)

publisher-build: ## Build publisher Docker image
	$(COMPOSE_LOCAL) build $(PUBLISHER_SERVICE)

publisher-logs: ## Tail publisher container logs
	$(COMPOSE_LOCAL) logs -f $(PUBLISHER_SERVICE)

# ------------------------------------------------------------------------------
# @section RabbitMQ (rabbit)
# ------------------------------------------------------------------------------

.PHONY: rabbit-up rabbit-down rabbit-down-v rabbit-restart rabbit-logs
rabbit-up: env ## Start RabbitMQ container
	$(COMPOSE) up -d $(RABBIT_SERVICE)

rabbit-down: ## Stop RabbitMQ container
	$(COMPOSE) stop $(RABBIT_SERVICE)

rabbit-down-v: ## Stop RabbitMQ and remove data volume
	$(COMPOSE) stop $(RABBIT_SERVICE)
	-$(COMPOSE) rm -f $(RABBIT_SERVICE)
	-docker volume rm $(PROJECT_NAME)_rabbitmq_data 2>/dev/null || true

rabbit-restart: ## Restart RabbitMQ container
	$(COMPOSE) restart $(RABBIT_SERVICE)

rabbit-logs: ## Tail RabbitMQ logs
	$(COMPOSE) logs -f $(RABBIT_SERVICE)

# ------------------------------------------------------------------------------
# @section Consumer
# ------------------------------------------------------------------------------

.PHONY: consumer-dev consumer-prod consumer-up consumer-down consumer-restart consumer-build consumer-logs
consumer-dev: env ## Run payment consumer locally (local profile)
	APP_ENV=$(APP_ENV_LOCAL) $(POETRY_RUN) python -m app.consumer.main

consumer-prod: env ## Run payment consumer locally (production profile)
	APP_ENV=$(APP_ENV_PRODUCTION) $(POETRY_RUN) python -m app.consumer.main

consumer-up: env ## Start consumer worker container
	$(COMPOSE) up -d $(CONSUMER_SERVICE)

consumer-down: ## Stop consumer worker container
	$(COMPOSE) stop $(CONSUMER_SERVICE)

consumer-restart: ## Restart consumer worker container
	$(COMPOSE) restart $(CONSUMER_SERVICE)

consumer-build: ## Build consumer Docker image
	$(COMPOSE) build $(CONSUMER_SERVICE)

consumer-logs: ## Tail consumer logs
	$(COMPOSE) logs -f $(CONSUMER_SERVICE)

.PHONY: nginx-up nginx-down nginx-down-v nginx-logs-prod
nginx-up: env ## Start nginx reverse proxy (production stack)
	$(COMPOSE_PROD) up -d $(NGINX_SERVICE)

nginx-down: ## Stop nginx container (production stack)
	$(COMPOSE_PROD) stop $(NGINX_SERVICE)

nginx-down-v: ## Stop nginx and remove container (production stack)
	$(COMPOSE_PROD) stop $(NGINX_SERVICE)
	-$(COMPOSE_PROD) rm -f $(NGINX_SERVICE)

nginx-logs-prod: ## Tail nginx logs (production stack)
	$(COMPOSE_PROD) logs -f $(NGINX_SERVICE)

# ------------------------------------------------------------------------------
# @section Database migrations (db)
# ------------------------------------------------------------------------------

.PHONY: db-migrate db-migrate-docker db-migrate-prod db-revision db-downgrade
db-migrate: env ## Apply Alembic migrations
	$(POETRY_RUN) alembic upgrade head

db-migrate-docker: env ## Apply migrations via local Docker migrate service
	$(COMPOSE_LOCAL) run --rm $(MIGRATE_SERVICE)

db-migrate-prod: env ## Apply migrations via prod Docker migrate service
	$(COMPOSE_PROD) run --rm $(MIGRATE_SERVICE)

db-revision: env ## Create new Alembic revision (use MSG='description')
	@test -n "$(MSG)" || (echo "Usage: make db-revision MSG='add payments table'" && exit 1)
	$(POETRY_RUN) alembic revision --autogenerate -m "$(MSG)"

db-downgrade: env ## Roll back one migration
	$(POETRY_RUN) alembic downgrade -1

# ------------------------------------------------------------------------------
# @section Code quality
# ------------------------------------------------------------------------------

.PHONY: lint lint-fix format test
lint: ## Run Ruff linter
	$(POETRY_RUN) ruff check .

lint-fix: ## Run Ruff linter with auto-fix
	$(POETRY_RUN) ruff check . --fix

format: ## Format code with Ruff
	$(POETRY_RUN) ruff format .

test: ## Run pytest
	$(POETRY_RUN) pytest

# ------------------------------------------------------------------------------
# @section Full stack
# ------------------------------------------------------------------------------

.PHONY: up up-prod down down-prod down-v down-v-prod restart ps logs
up: env ## Start local Docker stack (exposed ports)
	$(COMPOSE_LOCAL) up -d

up-prod: env ## Start production Docker stack (nginx :80, internal backend)
	$(COMPOSE_PROD) up -d

down: ## Stop local Docker stack
	$(COMPOSE_LOCAL) stop

down-prod: ## Stop production Docker stack
	$(COMPOSE_PROD) stop

down-v: ## Stop local stack, remove volumes, and remove prod nginx if running
	-$(COMPOSE_PROD) stop $(NGINX_SERVICE) 2>/dev/null || true
	-$(COMPOSE_PROD) rm -f $(NGINX_SERVICE) 2>/dev/null || true
	$(COMPOSE_LOCAL) down -v

down-v-prod: ## Stop prod stack, remove volumes, and remove nginx
	$(COMPOSE_PROD) down -v

restart: ## Restart local Docker stack
	$(COMPOSE_LOCAL) restart

ps: ## Show status of all containers
	$(COMPOSE_LOCAL) ps

logs: ## Tail logs of all services
	$(COMPOSE_LOCAL) logs -f
