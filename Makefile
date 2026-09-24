COMPOSE := docker compose
JOB     := $(COMPOSE) run --rm jobs
AS      ?= mara

.DEFAULT_GOAL := help
.PHONY: help init build up down reset load policy demo ask explain doctor cq test lint \
        leak verify-audit reset-audit boundary up-stores mcp-configs ps logs

help: ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-13s\033[0m %s\n", $$1, $$2}'

init: ## .env, per-persona keys, audit salt, one MCP config per persona (never overwrites a key)
	@./scripts/init.sh

mcp-configs: ## MCP configs for Claude Code on this machine; for a remote host: make mcp-configs HOST=ds1
	@./scripts/mcp-configs.sh $(HOST)

build: init ## Build the images, including the per-persona MCP image
	$(COMPOSE) --profile mcp --profile jobs build

up: init ## Start postgres, fuseki, opa and the resolver, and wait for health
	@test -f build/opa/data.json || (echo "no compiled policy yet — run: make up-stores load policy" && exit 1)
	$(COMPOSE) up -d --wait postgres fuseki opa resolver

up-stores: init ## Start only the stores (first run, before a policy has been compiled)
	$(COMPOSE) up -d --wait postgres fuseki

load: ## Seed the systems of record, map with R2RML, add told facts, validate, load
	$(JOB) load

policy: ## Compile barriers.yaml against the systems of record, test it, and restart OPA
	$(JOB) policy
	docker run --rm -v "$(CURDIR)/policy:/policy:ro" openpolicyagent/opa:1.9.0-static test /policy
	$(COMPOSE) up -d --wait --force-recreate opa resolver

demo: ## The M1 scenes, asked as the personas, through the resolver
	$(JOB) demo

ask: ## One question as one persona: make ask Q=CQ-06 AS=sanne S="matter=M-2022-0117"
	$(JOB) ask $(or $(Q),CQ-02) --as $(AS) $(foreach s,$(S),--set $(s))

explain: ## Why a trace was decided as it was: make explain T=t-1a2b3c4d AS=sanne
	$(JOB) explain $(T) --as $(AS)

leak: ## The barrier suite — every rule, every persona, four shapes → reports/leak.md
	$(JOB) leak

verify-audit: ## Recompute the decision record's hash chain; name the first broken record
	$(JOB) verify-audit

reset-audit: ## Start a fresh decision record (before a demo, so the trail is the one they watch)
	@rm -f audit/decisions.jsonl && echo "audit/decisions.jsonl removed — the next request starts a new chain"

boundary: ## Prove the MCP container reaches the resolver and nothing else
	@docker run --rm --network tkg_edge --entrypoint python tkg-mcp:latest \
	  -c "import socket; socket.gethostbyname('resolver')" \
	  && echo "resolver  reachable from the MCP container" \
	  || (echo "resolver  NOT reachable — is the stack up?" && exit 1)
	@for h in fuseki opa postgres; do \
	  if docker run --rm --network tkg_edge --entrypoint python tkg-mcp:latest \
	       -c "import socket; socket.gethostbyname('$$h')" 2>/dev/null; \
	  then echo "$$h  REACHABLE — the boundary is broken"; exit 1; \
	  else echo "$$h  not reachable"; fi; \
	done

doctor: ## Check every service is reachable
	$(JOB) doctor

cq: ## List the competency questions
	$(JOB) cq

test: ## Unit tests and the policy's own tests
	$(COMPOSE) run --rm --entrypoint pytest jobs -q
	docker run --rm -v "$(CURDIR)/policy:/policy:ro" openpolicyagent/opa:1.9.0-static test /policy

lint: ## Ruff, and the Rego formatter
	$(COMPOSE) run --rm --entrypoint ruff jobs check src tests
	docker run --rm -v "$(CURDIR)/policy:/policy:ro" openpolicyagent/opa:1.9.0-static fmt --fail --list /policy

ps: ## What is running
	$(COMPOSE) ps

logs: ## Tail the logs
	$(COMPOSE) logs -f --tail=80

down: ## Stop, keep the data
	$(COMPOSE) down

reset: ## Stop and drop every volume — the stores are disposable by design
	$(COMPOSE) down -v
