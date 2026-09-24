COMPOSE := docker compose
JOB     := $(COMPOSE) run --rm jobs

.DEFAULT_GOAL := help
.PHONY: help init build up down reset load demo ask doctor cq test lint ps logs

help: ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

init: ## Create .env from the example (does not overwrite)
	@test -f .env || (cp .env.example .env && echo "wrote .env")
	@test -f .env && echo ".env present"

build: init ## Build the images
	$(COMPOSE) build

up: init ## Start postgres, fuseki and the resolver, and wait for health
	$(COMPOSE) up -d --wait postgres fuseki resolver

load: ## Seed the systems of record, map with R2RML, validate the shapes, load
	$(JOB) load

demo: ## Answer every competency question from the spine
	$(JOB) demo

ask: ## Answer one: make ask Q=CQ-02
	$(JOB) ask $(or $(Q),CQ-02)

doctor: ## Check both stores are reachable
	$(JOB) doctor

cq: ## List the competency questions
	$(JOB) cq

test: ## Unit tests, in the image that runs the lab
	$(COMPOSE) run --rm --entrypoint pytest jobs -q

lint: ## Ruff
	$(COMPOSE) run --rm --entrypoint ruff jobs check src tests

ps: ## What is running
	$(COMPOSE) ps

logs: ## Tail the logs
	$(COMPOSE) logs -f --tail=80

down: ## Stop, keep the data
	$(COMPOSE) down

reset: ## Stop and drop every volume — the stores are disposable by design
	$(COMPOSE) down -v
