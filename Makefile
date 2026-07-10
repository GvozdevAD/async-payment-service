.DEFAULT_GOAL := help

# Help convention:
#   # @section Block name  — group header in `make help`
#   target: [deps] ## Description — appears under the current section

PROJECT_NAME     ?= test-task
COMPOSE          := docker compose -p $(PROJECT_NAME)
PG_SERVICE       := postgres
API_SERVICE      := api
RABBIT_SERVICE   := rabbitmq
CONSUMER_SERVICE := consumer

API_HOST         ?= 0.0.0.0
API_PORT         ?= 8000
POETRY_RUN       := poetry run
UVICORN          := $(POETRY_RUN) uvicorn app.main:app

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
	poetry install

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

.PHONY: api-dev api-up api-down api-restart api-build api-logs gen-openapi
api-dev: env ## Run API locally with hot reload
	$(UVICORN) --reload --host $(API_HOST) --port $(API_PORT)

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

.PHONY: consumer-up consumer-down consumer-restart consumer-build consumer-logs
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

# ------------------------------------------------------------------------------
# @section Database migrations (db)
# ------------------------------------------------------------------------------

.PHONY: db-migrate db-revision db-downgrade
db-migrate: env ## Apply Alembic migrations
	$(POETRY_RUN) alembic upgrade head

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

.PHONY: up down down-v restart ps logs
up: env ## Start all services
	$(COMPOSE) up -d

down: ## Stop all services
	$(COMPOSE) stop

down-v: ## Stop all services and remove volumes
	$(COMPOSE) down -v

restart: ## Restart all services
	$(COMPOSE) restart

ps: ## Show status of all containers
	$(COMPOSE) ps

logs: ## Tail logs of all services
	$(COMPOSE) logs -f
