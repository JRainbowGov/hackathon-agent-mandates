# Dev scaffold: audit store and tracing

Infrastructure for the planned audit, history and budget layers. **No gateway decision changes yet.** The gateway
can reach a Postgres store and send traces, but nothing reads or writes the tables. Without the override file the
stack runs exactly as before.

## Start it

```bash
make obs_up      # = docker compose -f docker-compose.yaml -f docker-compose.observability.yaml up -d --build --wait
make obs_down    # stop; keeps the Postgres volume
make obs_reset   # stop and drop the volume, so db/init/ runs again on the next obs_up
```

The override's variables come from `.env`. If your `.env` predates this change, copy the `POSTGRES_*`,
`GATEWAY_DB_*`, `POSTGRES_HOST_PORT` and `JAEGER_UI_PORT` lines over from `.env.example`. Compose refuses to start
and names the missing variable. The values are placeholders, so change them locally and never commit real ones.

What the override adds:

| Service | What | Host port (127.0.0.1 only) |
| --- | --- | --- |
| `postgres` | `postgres:17-alpine`, volume `gateway-pgdata`, init scripts from `db/init/`. Healthy once the gateway role can log in and read `gateway.schema_version` | `${POSTGRES_HOST_PORT:-55432}` |
| `jaeger` | `jaegertracing/jaeger:2.10.0` all-in-one: OTLP receiver and UI, in-memory trace storage | UI `${JAEGER_UI_PORT:-16686}`, OTLP/HTTP `${OTLP_HTTP_HOST_PORT:-4318}` |
| `gateway` (extended) | `GATEWAY_DATABASE_URL`, `OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318`, `OTEL_SERVICE_NAME=mandate-gateway`; waits for Postgres to be healthy | unchanged |

Jaeger was picked because a single container takes OTLP and serves a UI. It keeps traces in memory, so they are
lost on restart, which is fine for dev.

## Traces

`make trace_ui` prints the URL, by default <http://127.0.0.1:16686/search?service=mandate-gateway>. Each
`POST /tools/call` is one trace. The server span carries the decision. On ALLOW it has child spans for the
upstream call: fastmcp's `tools/call <tool>` and the MCP library's `MCP send …` spans. The MCP client talks over
`httpx2`, which the httpx instrumentor doesn't hook. That instrumentor covers other outbound `httpx` calls,
such as a model call through litellm.

**Traces carry no pupil data.** Everything is in [gateway/lib/telemetry.py](../gateway/lib/telemetry.py):

- The gateway adds only `gateway.server`, `gateway.tool`, `gateway.decision`, `gateway.reason_code`,
  `gateway.policy_version`, `gateway.arg_keys` (argument names) and `gateway.jti_hash` (sha256 of the jti). It never
  adds argument values, results or `Decision.detail`, because detail can quote an argument (`urn='SCH07'`).
- Every exported span goes through a redacting exporter. Only attribute keys in `ALLOWED_ATTRIBUTES` survive,
  events keep only `exception.type`, and status descriptions are blanked. This also covers spans made by other
  libraries: fastmcp copies tool-error text into span status, and exception events carry messages. Query strings
  (`http.target`, `url.full`, `url.query`) are not allowlisted.
- `/healthcheck` and `/healthcheck/db` are not traced.
- Tracing is off unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set. When it is off, the OTel SDK is not even imported.

[gateway/tests/test_telemetry.py](../gateway/tests/test_telemetry.py) checks that argument values and the jti
never reach an exported span.

## The audit store

Schema: [db/init/01_schema.sql](../db/init/01_schema.sql), everything in the `gateway` schema. Roles:
[db/init/02_gateway_role.sh](../db/init/02_gateway_role.sh).

| Table | For |
| --- | --- |
| `audit_events` | Append-only, hash-chained decision log: who (jti, agent_id, iss, principal, parent_jti), what (server, tool, `arg_keys`, `arg_hash`, scoped urn and pupil_id), the decision and reason_code, the model guardrail's label, confidence and version, and what came back (`rows_returned`, `pupil_ids_returned`, `max_pii_level`). Chain columns are `prev_hash`, `event_hash` and `sig`. `UNIQUE(prev_hash)` stops the chain forking |
| `nonces` | Replay set, to replace the in-memory `Gateway._seen_nonces`; `expires_at` for pruning |
| `budget_counters` | Calls and rows per (jti, tool, window) |
| `mandate_pupils` | Distinct pupils seen per mandate, with the highest PII level |
| `suspensions` | Gateway-owned deny list by jti, agent_id, iss or principal. Separate from the issuer's status list, because the issuer key does not live on the gateway |
| `schema_version` | Current schema version (1) |

Identifiers and PII levels only, never data values. Arguments are stored as keys plus a hash.

**Append-only is enforced twice.** The gateway connects as `GATEWAY_DB_USER`, which has `SELECT, INSERT` on
`audit_events` and no `UPDATE`, `DELETE` or `TRUNCATE`. Triggers then refuse those statements for every role,
including the owner. Only `DROP TRIGGER` by the owner gets past them.

Inspect it:

```bash
make db_shell            # as the owner (POSTGRES_USER)
make db_shell_gateway    # as the gateway role
```

```sql
\dt gateway.*
\d gateway.audit_events
SELECT * FROM gateway.schema_version;
```

Gateway-side DB health: `curl localhost:8082/healthcheck/db` returns `{"status":"ok","schema_version":1}`,
`{"status":"disabled"}` without the override, or a 503 if the database can't be reached. The container probe
`/healthcheck` never touches the DB.

### Migrating later

`db/init/` runs only when the volume is empty, so a schema change does not reach an existing volume. Until there
is real data, change `01_schema.sql`, bump `schema_version` and run `make obs_reset`. Once data matters, switch to
numbered forward-only migrations applied at gateway start (a `db/migrations/NNN_*.sql` runner, or Alembic) that
check `schema_version`. Freeze `01_schema.sql` as migration 001 at that point.

## Day 2: don't publish these

Host ports bind to `127.0.0.1`. On a deployed gateway, do not expose Postgres or the Jaeger UI and OTLP ports: the
UI has no auth, and an open OTLP port lets anyone inject spans. If you deploy with the override, drop the `ports:`
on `postgres` and `jaeger`, or keep them on a private network, and replace the placeholder passwords.

## Not done yet (later changes)

- Writing `audit_events` from `tools_call`: computing `arg_hash`, the chain, the gateway signature and the result
  summary (rows, pupil IDs, max PII level).
- DB-backed nonces in `Gateway.decide`, budgets and distinct-pupil limits, suspension checks, and history-aware
  rules. Each needs a reason_code and has to fail closed on DB errors. `db.get_pool()` raises when there is no DB.
- A chain verifier (walk `prev_hash` → `event_hash`, check `sig`), and a CLI to add or lift suspensions.
- A migration runner (see above), trace sampling, metrics and logs over OTLP, and tracing the decision model call.
