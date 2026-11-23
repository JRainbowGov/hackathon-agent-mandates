## 1. Prerequisites

- [ ] 1.1 Merge `feature/dev-scaffold` into main (push the branch, open a PR, merge), then rebase `feature/audit-trail` onto it; verify `gateway/lib/db.py` and `db/init/01_schema.sql` exist on this branch and `make test` passes
- [ ] 1.2 Agree the `MANDATE_MALFORMED` catch-all and the `policy_version` field with the access-config workstream; verify by a note in this change's design (or their PR) naming who lands the catch-all

## 2. Decision context and catch-all

- [ ] 2.1 Add `AuditContext` and `Gateway.decide_with_context` in `gateway/lib/gateway_verify.py` (verified claims, or claimed `jti`/`iss` read without verification, plus scope `urn`/`pupil_id`), with `decide` as a wrapper; verify existing gateway tests pass unchanged
- [ ] 2.2 Turn any non-`Reject` exception in `decide_with_context` into `DENY MANDATE_MALFORMED`; verify with tests for `"garbage"` and a JWT payload with no `iss`, both returning 403 instead of 500
- [ ] 2.3 Add `audit` at level 2 to `SERVER_LEVELS` in `gateway/lib/interfaces.py`; verify a test that a `clearance: 1` mandate gets `CLEARANCE_TOO_LOW` on `audit.events` and a mandate without clearance gets `CLEARANCE_MISSING`

## 3. Audit core

- [ ] 3.1 Create `gateway/lib/audit.py` with the event model, canonical hashing (sorted arrays, ISO UTC timestamps) and Ed25519 signing with `gateway_key.pem`; verify unit tests that the same event hashes identically twice and that a changed field changes the hash
- [ ] 3.2 Implement `summarise(server, tool, result)` (rows, pupil IDs under `Psuedo ID`/`pupil_id`, columns, max PII level from the manifest with level 4 for unlisted columns, result hash); verify unit tests on a census search result, the schools file (level 1, no pupils) and a `draft` result
- [ ] 3.3 Implement `MemoryStore` (append under a lock, head, query by principal/jti/time with a 500 cap, history); verify unit tests for chain linkage, first-event zero hash and the query cap
- [ ] 3.4 Write `db/init/03_audit_v2.sql` (new columns, nullable `decision` with a check for decision events) and a note in `docs/dev-scaffold.md`; verify `make obs_reset && make obs_up` starts healthy and `\d gateway.audit_events` shows the new columns
- [ ] 3.5 Implement `PostgresStore` with the advisory-lock append transaction and the same query and history methods; verify an integration test (skipped without `GATEWAY_DATABASE_URL`) that appends 50 events concurrently and gets one unbroken chain
- [ ] 3.6 Implement `history(jti)` (calls per tool, reason counts, distinct pupils, max PII level, refusals in a row, first and last time; verified events only) and `record_external` for approval events; verify unit tests including a forged event that doesn't change another mandate's history

## 4. Gateway wiring

- [ ] 4.1 In `gateway/main.py` `tools_call`, use `decide_with_context`, add `decision_id` to the `decision` object, record one event per call with source address (trusted-proxy rule) and HTTP status; verify tests that ALLOW, DENY, STEP_UP and a pre-signature refusal each produce exactly one event whose `decision_id` matches the response
- [ ] 4.2 Withhold results and return `503 AUDIT_UNAVAILABLE` when an allowed call's event can't be written, and still return refusals; verify with a store that raises on append
- [ ] 4.3 Dispatch `server == "audit"` to an in-process handler for `events` and `saw` after the normal checks, never to an MCP client; verify tests for an own-principal read (200), another principal (403 `CONSTRAINT_VIOLATED`), the default mandate (403), claimed events listed separately, and the read itself being recorded
- [ ] 4.4 Implement `audit.saw` output with the plain-words sentence and revoked status from the status list; verify tests for a used-then-revoked mandate and a never-used one
- [ ] 4.5 Add `GET /audit/head`; verify a test that it returns only `seq`, `event_hash` and `sig`
- [ ] 4.6 Mount the manifest read-only into the gateway and set `GATEWAY_MANIFEST_PATH` in `docker-compose.yaml`; verify after `docker compose up -d --build gateway` that a live census search's event has `max_pii_level` 4

## 5. CLI

- [ ] 5.1 Add `cli audit anchor --url` (append head to a local file) and `cli audit verify --db --anchors` (hashes, signatures, links, anchors); verify a test that an edited `reason_code` and a replaced chain are each reported
- [ ] 5.2 Add `cli audit saw --jti` and `cli audit events --principal|--jti`, which sign an `audit` call with a reader mandate and key; verify against the live stack that they print the same data as the tool calls

## 6. Docs and check-in

- [ ] 6.1 Write `docs/audit-trail.md` laid out like `questions/02-worked-example.md`: an audit-reader mandate, a request it allows, one it denies, the `audit.saw` output after a revoke, and what's unresolved; verify each command in it runs on a fresh `make hack`
- [ ] 6.2 Add `audit` events to `gateway/lib/mandate.schema.json` docs (reader scope form); verify the file still parses as JSON

## 7. Final checks

- [ ] 7.1 `make eval_run` gives the same decisions and reason codes as before (question 0 at 12/12), with the memory store and with Postgres
- [ ] 7.2 `make test` passes, including the new audit tests
- [ ] 7.3 `make lint` passes
- [ ] 7.4 `docker compose up -d --build gateway` (and `make obs_up` for Postgres), then one allowed, one refused and one forged call show up via `cli audit events`, and `cli audit verify` reports the chain intact
