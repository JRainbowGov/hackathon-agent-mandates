## Why

The gateway decides every call and remembers none of them (`tools_call` in `gateway/main.py` discards the decision record). So a person can't find out what their agent took after revoking it (question 14), or who used their access (question 16), and the history-aware layers (Tom's flow enforcement, budgets, the decision model) have nothing to read. On Day 2 the "Unseen" bonus also scores against teams that can't find a landed flag in their own records within 5 minutes.

## What Changes

- Every `POST /tools/call` writes one audit event: ALLOW, STEP_UP and DENY, including refusals before the mandate or request signature verifies. For those, the claimed `jti` and `iss` are stored and marked unverified.
- Every response carries a `decision_id` inside the existing `decision` object. The request shape is unchanged.
- For an allowed call, the event records what came back: rows returned, pupil IDs, column names, highest PII level, and a hash of the result. Argument values are never stored, except the school and pupil values the scope constrains.
- Events form a hash chain, each signed with the gateway key. `GET /audit/head` publishes the latest signed head, and a CLI lets anyone outside the gateway anchor heads and later verify the chain against them.
- Reading the audit trail is itself a mandated call: `server: "audit"` through the same `POST /tools/call`, with an issuer-signed audit-reader mandate. A reader sees only events for mandates they are allowed to read. An operational mandate, or a stolen agent key, can't read the log.
- Two read tools: `audit.events` (the request log, question 16) and `audit.saw` (what a mandate received, question 14, in plain terms).
- An in-process history API, `record`, `events(jti)` and `history(jti)`, for flow rules and budgets. It also records approval events from the human-in-the-loop workstream.
- Storage: Postgres from the dev scaffold when `GATEWAY_DATABASE_URL` is set; otherwise an in-memory store, so the base stack, tests and the eval still get a working, non-durable log.
- Fail closed: if the configured store can't write an event, the gateway withholds the result and returns `503` with reason `AUDIT_UNAVAILABLE`. Decisions are otherwise unchanged.

## Capabilities

### New Capabilities
- `audit-trail`: recording one tamper-evident event per gateway decision, what came back, the `decision_id`, the hash chain and its external anchoring, and behaviour when the store fails.
- `audit-access`: who may read audit events and how (audit-reader mandates through `POST /tools/call`), the `audit.events` and `audit.saw` tools, and the in-process history API other layers use.

### Modified Capabilities
- `mandate-clearance`: the list of server data levels gains `audit` at level 2, so reading the trail needs clearance 2 and a mandate without clearance is refused.

## Non-goals

- No change to any ALLOW, STEP_UP or DENY decision, for mandates with or without new claims. Audit only records; budgets, suspensions and flow rules that act on history are separate changes.
- No approval workflow. The human-in-the-loop workstream owns approvals; this change only accepts their events.
- No DB-backed nonces, budgets or suspensions, though the scaffold has tables for them.
- No redaction pipeline or trace export. Events hold IDs and levels, never values.
- No multi-replica support beyond what Postgres gives for free.

## Impact

- **Depends on** `feature/dev-scaffold` (Postgres schema, `gateway/lib/db.py`) being merged to main first.
- **Code:** new `gateway/lib/audit.py` (event model, summariser, chain, stores, history API); `gateway/main.py` (record every decision, `decision_id`, the `audit` server, `GET /audit/head`); small hook in `gateway/lib/gateway_verify.py` to expose unverified `jti` and `iss` on early refusals; `gateway/cli.py` (`audit anchor`, `audit verify`, `audit saw`).
- **DB:** migration `db/init/03_audit_v2.sql` adds columns the scaffold lacks (event type, verified flag, columns returned, result hash, policy version, mandate hash, source address, HTTP status).
- **Response:** `decision.decision_id` is a new field. Existing fields and status codes are unchanged, so the eval and other teams' clients are unaffected.
- **Questions:** 14, 16; inputs for 9, 11, 12. Day 2: "Unseen" bonus; makes the log a target, so reads are mandated and audited.
