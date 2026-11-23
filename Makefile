-include .env
export

# Docker image, terraform and release targets live in platform.mk. Teams never need them.
-include platform.mk

install:
	cd frontend && npm install
	uv sync --extra fastapi --extra gateway --extra synth
	docker compose build 

.PHONY: synth
synth:  ## Regenerate mcp_server/data/synthetic (pupil census, deprivation, schools, display names) from mcp_server/synth/synth.yaml
	uv run python -m mcp_server.synth

hack: install  ## One command start: keys, one-school mandate, eval pack, containers, first signed call
	cp -n .env.example .env || true
	test -f gateway/state/trusted_list.json || uv run python -m gateway.cli init
	uv run python -m gateway.cli issue --agent-key gateway/state/agent.pem -o gateway/state/mandate.jwt
	uv run python -m gateway.eval build -o eval_pack
	docker compose up -d --wait
	uv run python -m gateway.cli call --mandate gateway/state/mandate.jwt --agent-key gateway/state/agent.pem \
		--tool search --args '{"query": "P0004", "urn": "SCH01"}'

run:
	docker compose up -d --wait

stop:
	docker compose down

gateway_init:  ## Generate gateway keys, trusted list and status list in gateway/state
	uv run python -m gateway.cli init

gateway_issue:  ## Issue a default one-school (SCH01) mandate to gateway/state/agent.pem
	uv run python -m gateway.cli issue --agent-key gateway/state/agent.pem -o gateway/state/mandate.jwt

eval_build:  ## Mint the eval mandates + keys from gateway/state into eval_pack/
	uv run python -m gateway.eval build -o eval_pack

eval_run:  ## Fire the eval cases for questions 0 to 5 at GATEWAY_URL (default localhost:8082)
	uv run python -m gateway.eval run --pack eval_pack --url $${GATEWAY_URL:-http://localhost:8082}

attack_mandates:  ## Day 2: issue the default mandate, and a feature mandate if FEATURE_SCOPE/FEATURE_CLAIMS are set, to each day_2_attack/keys/<team>.jwk
	mkdir -p day_2_attack/keys day_2_attack/mandates
	for key in day_2_attack/keys/*.jwk; do \
		[ -e "$$key" ] || { echo "no keys in day_2_attack/keys"; exit 1; }; \
		team=$$(basename "$$key" .jwk); \
		uv run python -m gateway.cli issue --agent-key "$$key" --ttl 86400 -o "day_2_attack/mandates/$$team.jwt" \
			--principal "attacker:$$team" --purpose "Day 2 attack mandate for $$team"; \
		if [ -n "$(FEATURE_SCOPE)$(FEATURE_CLAIMS)" ]; then \
			uv run python -m gateway.cli issue --agent-key "$$key" --ttl 86400 -o "day_2_attack/mandates/$$team.feature.jwt" \
				--principal "attacker:$$team" --purpose "Day 2 feature mandate for $$team" \
				$(if $(FEATURE_SCOPE),--scope "$$(cat $(FEATURE_SCOPE))") $(if $(FEATURE_CLAIMS),--claims "$$(cat $(FEATURE_CLAIMS))"); \
		fi; \
	done

test:
	cd mcp_server && uv sync --group dev --extra fastapi --extra gateway --extra synth && uv run python -m pytest --cov=mcp_server -v --cov-report=term-missing --cov-fail-under=0
	uv run python -m pytest gateway/tests data_slices/tests

.PHONY: lint
lint:  ## Check code formatting & linting
	uv run ruff format . --check
	uv run ruff check .

.PHONY: format
format:  ## Format and fix code
	uv run ruff format .
	uv run ruff check . --fix

# ---------------------------------------------------------------- dev-only audit store + tracing (docs/dev-scaffold.md)
OBS_COMPOSE = docker compose -f docker-compose.yaml -f docker-compose.observability.yaml

.PHONY: obs_up obs_down obs_reset db_shell db_shell_gateway trace_ui
obs_up:  ## Start the stack plus Postgres and Jaeger; the gateway traces to Jaeger
	cp -n .env.example .env || true
	$(OBS_COMPOSE) up -d --build --wait

obs_down:  ## Stop the stack and the observability services; keeps the Postgres volume
	$(OBS_COMPOSE) down

obs_reset:  ## Stop everything and drop the Postgres volume, so db/init runs again on the next obs_up
	$(OBS_COMPOSE) down --volumes

db_shell:  ## psql into the audit store as the schema owner
	$(OBS_COMPOSE) exec postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

db_shell_gateway:  ## psql as the gateway's own role (append-only on audit_events)
	$(OBS_COMPOSE) exec postgres sh -c 'PGPASSWORD="$$GATEWAY_DB_PASSWORD" psql -h 127.0.0.1 -U "$$GATEWAY_DB_USER" -d "$$POSTGRES_DB"'

trace_ui:  ## Print the Jaeger UI URL
	@echo "http://127.0.0.1:$${JAEGER_UI_PORT:-16686}/search?service=mandate-gateway"

run_frontend:
	cd frontend && npm run dev

run_backend:
	uv run python -m uvicorn mcp_server.main:app --reload

pre-commit-install:
	pre-commit install

.PHONY: safe
safe:
	uv run bandit -ll -r ./mcp_server
