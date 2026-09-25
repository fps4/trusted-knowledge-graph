COMPOSE := docker compose
JOB     := $(COMPOSE) run --rm jobs
AS      ?= mara

.DEFAULT_GOAL := help
.PHONY: help init build up down reset load policy demo ask explain doctor cq test lint \
        leak verify-audit reset-audit boundary up-stores mcp-configs term audit glossary reports sali documents extract extraction naive eval eval-live baseline gate review ps logs

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
	$(COMPOSE) up -d --wait postgres fuseki opa minio opensearch resolver

up-stores: init ## Start only the stores (first run, before a policy has been compiled)
	$(COMPOSE) up -d --wait postgres fuseki minio opensearch

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

term: ## What a business word means, and who owns that: make term W="active client" AS=sanne
	$(JOB) term "$(or $(W),active client)" --as $(AS)

audit: ## The three governance questions as Risk, over the last run → reports/audit.md
	$(JOB) audit-report

glossary: ## Terms, readings and their counts, SALI mapping, relations → reports/glossary.md
	$(JOB) glossary-report

reports: ## Regenerate everything under reports/ from a fresh record
	@rm -f audit/decisions.jsonl
	$(JOB) demo > /dev/null
	$(JOB) audit-report
	$(JOB) glossary-report
	-$(JOB) extraction-report
	$(JOB) eval
	$(JOB) leak
	$(JOB) verify-audit

documents: ## Regenerate the firm's documents and the gold-set manifest from the estate
	$(JOB) documents

extract: ## Extraction through Claude (Batches API) → data/fixtures/extraction.jsonl — needs ANTHROPIC_API_KEY in .env
	$(JOB) extract $(if $(LIMIT),--limit $(LIMIT)) $(if $(MISSING),--missing) $(if $(RESUME),--resume $(RESUME))

extraction: ## Precision and recall against the manifest → reports/extraction.md
	$(JOB) extraction-report

naive: ## The vector-only comparison, no access decision: make naive Q="who led the AFM settlement"
	$(JOB) naive "$(Q)"

eval: ## Thirty questions, both paths → reports/eval.md (graph live; vector from fixture)
	$(JOB) eval

eval-live: ## Regenerate the vector path's composed answers and verdicts with Claude — needs ANTHROPIC_API_KEY
	$(JOB) eval --live

baseline: ## Record the current eval as the bar the gate holds
	$(JOB) eval --baseline

gate: ## The deploy gate: policy fresh, zero leaks, store agrees with OPA, eval ≥ baseline, chain intact
	$(JOB) gate

review: ## Facts awaiting review on a matter: make review M=M-2022-0022 AS=kim
	$(JOB) review list $(M) --as $(AS)

sali: ## Re-import the SALI LMSS subset at the commit pinned in config/sali-mapping.yaml (network)
	python3 scripts/sali-subset.py

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
	$(COMPOSE) run --rm -e RUFF_CACHE_DIR=/tmp/ruff --entrypoint ruff jobs check src tests
	docker run --rm -v "$(CURDIR)/policy:/policy:ro" openpolicyagent/opa:1.9.0-static fmt --fail --list /policy

ps: ## What is running
	$(COMPOSE) ps

logs: ## Tail the logs
	$(COMPOSE) logs -f --tail=80

down: ## Stop, keep the data
	$(COMPOSE) down

reset: ## Stop and drop every volume — the stores are disposable by design
	$(COMPOSE) down -v
