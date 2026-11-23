## 1. Prerequisites

- [ ] 1.1 Before starting, rebase again onto the latest `ihor` (first rebased 23 Nov onto the audit trail and the question 3–5 fixes); verify `gateway/lib/audit.py` has `record_external` and `Gateway.decide_with_context` exists, and `make eval_run` is 32/32
- [ ] 1.2 Agree two things with the audit workstream: (a) results of `grants` and `audit` are scored at their server level, not as level-4 flat dicts; (b) the issuer's signed approval events reach `record_external` through the gateway's internal endpoint. Verify by a dated note in this change's design or their PR for each. (`decision_id` before forwarding is already done.)
- [ ] 1.3 Agree with the access-config workstream that `/demo/*` moves behind the issuer service and an env flag; verify by a note naming who lands it
- [ ] 1.4 After the rebase, re-copy the "Every server has a data level" and "Every special call is held for approval" requirements from main's `openspec/specs/mandate-clearance/spec.md` into this change's delta and re-apply only this change's edits (`grants` 1, the pre-approval exception); verify `openspec validate add-scope-requests --strict` passes and the delta keeps every scenario main has

## 2. Mandate audience

- [ ] 2.1 Read `audience` in `check_request`: `AUDIENCE_INVALID` for any form other than `{"pupils": [...]}` (1–500 IDs), `AUDIENCE_VIOLATED` for `pupil_id` or any `pupil_ids` value outside it; verify unit tests for the three `mandate-audience` scenarios that name pupils
- [ ] 2.2 Check that entries without `audience` behave as before; verify the existing gateway tests and `make eval_run` give identical decisions and reason codes

## 3. Tool grants

- [ ] 3.1 Create `gateway/lib/tool_grant.py` with `mint` and `verify` (typ `tool-grant+jwt`, EdDSA by `tool_grant_key.pem`, claims per spec, 30 s expiry, 5 s skew) and `cli init` generating the key; verify unit tests for a valid grant and for each refusal reason (`GRANT_INVALID`, `GRANT_EXPIRED`, `GRANT_MISMATCH` on changed args, tool or `aud`)
- [ ] 3.2 Derive grants only from verified claims and the matched entry (`urns` from the `urn` constraint, `pupils` from `audience`, `level` = min(server level, clearance), `max_rows` default 100), with `jti` = `decision_id`; verify a unit test that an extra `urn` or `clearance` argument doesn't change the grant
- [ ] 3.3 Pass `decision_id` into `_forward` and send the grant with `StreamableHttpTransport(url, headers={"X-Tool-Grant": ...})` for URL targets only; verify a gateway test with a stub HTTP server that receives the header and an in-process test that still works without it
- [ ] 3.4 Add the grant-verifying middleware, a `check_args` helper (arguments against subjects and constraints, giving `GRANT_SCOPE`) and an `enforce` helper (subjects, level, `max_rows`) with a seen-`jti` set, to `mcp_server`; pass `initialize` and `tools/list` through, behind `TOOL_GRANTS=enforce|off` with no default. Verify that `curl` to `:8080/mcp/` with a `tools/call` returns `GRANT_MISSING`, that `GET /describe` still lists tools, and that `make test` passes
- [ ] 3.5 Apply `enforce` in every `pupil-data` tool's output (`search`, `get`, `aggregate`, `roster`, `pupil`, `draft`, `write`, `classification`); verify a test per tool that a grant for `SCH01` returns no `SCH02` data even when the arguments ask for it
- [ ] 3.6 Add the same middleware, `check_args` and `enforce` to the three slices; verify a test that `directory.roster` with a grant whose `subjects.pupils` is `["P0011","P0042"]` returns only those two, and that a grant for `SCH04` with `urn="SCH02"` in the arguments returns `GRANT_SCOPE`
- [ ] 3.7 Set `TOOL_GRANTS=enforce` in `docker-compose.yaml` for backend and slices, and mount the tool-grant public key; verify with `docker compose up -d --build` that the full eval gives the same decisions and the same result rows as with `TOOL_GRANTS=off` (parity script in `gateway/tests/`)

## 4. Issuer service

- [ ] 4.1 Create `issuer/` (FastAPI JSON API only, Dockerfile, Compose service) mounting `issuer_key.pem`, `status_list.json`, `principals.json`, `approvers.json` and `requests.db`, and publishing `status_list.jwt` to a volume the gateway reads; verify `make hack` brings it up healthy and `cli revoke` still takes effect on the next gateway call
- [ ] 4.2 Remove the issuer private key from the gateway mount (mount only `trusted_list.json`, `status_list.jwt`, `tool_grant_key.pem` and the audit key); verify `docker compose exec gateway ls /app/gateway/state` shows no `issuer_key.pem` and the eval still passes
- [ ] 4.3 Implement the request store (SQLite; create, get, pending count, requests in the last hour, identical recent rejection, single-decision conditional update, expiry sweep); verify unit tests for one decision only, expiry after 15 minutes, and each throttle count
- [ ] 4.4 Implement `POST /requests` and the supervisor-decision endpoint so the issuer re-verifies every forwarded signed body itself (its own signature on the mandate, dates, revocation, the agent's or supervisor's request signature, its own nonce set). Mint only on a person decision verified with the approver key or a supervisor decision verified the same way, re-check the principal ceiling, and mint per the spec (same `cnf`, `parent`, `approved_by`, `preapproved` with 5-minute expiry, exp ≤ parent). Verify the "gateway can't mint on its own", "forged requester", "same key, only the new grant" and "never outlives the parent" scenarios
- [ ] 4.5 Add `cli approver keygen`, `cli approve` and `cli approver-login` (5-minute single-use login token) with `approvers.json` registration; verify a test that another principal's key and a reused login token are refused
- [ ] 4.6 Add the issuer's signed event outbox and the gateway's internal `POST /internal/audit-events`, which verifies the issuer signature and calls `record_external`; verify that a person's approval appears in `audit.events` without the agent polling, and that an unsigned post is refused

## 5. The grants server

- [ ] 5.1 Add `grants` at level 1 to `SERVER_LEVELS`, the implicit scope rule, `deny`-rule handling and dispatch in `tools_call`; verify tests for the three scenarios of "grants server is reached through the normal call path" and the clearance-missing scenario
- [ ] 5.2 Implement `grants.self` with the plain-words summary generator (school names from the schools file, tool descriptions, expiry in local time); verify the plain-words scenario
- [ ] 5.3 Implement `grants.check` reusing `check_request`, clearance and audience without forwarding or minting, plus the missing-grant computation; verify the missing-school and no-side-effect scenarios
- [ ] 5.4 Implement `grants.request` with validation (`REQUEST_INVALID`, `EXCEEDS_PRINCIPAL`, `already_granted`), held-call requests checked against the held call's audit event (same mandate, `STEP_UP`, same server, tool and argument hash), throttling from the issuer's request store (`TOO_MANY_REQUESTS`, `RECENTLY_REJECTED`), and the full result contract (`user_code` without look-alike characters, summary, text, `next_action`); verify a test per scenario, including "held call with different arguments"
- [ ] 5.5 Implement `grants.status` and `grants.decide` (supervisor path: `can_delegate`, same principal, coverage, `EXCEEDS_SUPERVISOR`, `SELF_APPROVAL`, `ALREADY_DECIDED`); verify a test per scenario
- [ ] 5.6 Record `approval_requested`, `approval_granted`, `approval_denied`, `approval_expired` and refused decisions through `record_external`; verify the "person can see who approved" scenario through `audit.events`

## 6. Parent, pre-approval and approval page

- [ ] 6.1 Add the `parent` revocation check to `verify_mandate` (`PARENT_REVOKED`, `STATUS_UNAVAILABLE`); verify the parent-revoked scenario
- [ ] 6.2 Add `action_hash` and the pre-approved step-up exception, with single use recorded in a `preapproval_uses` table (SQLite at `GATEWAY_STATE_DB` on the `gateway-audit` volume, otherwise memory) under a unique key before forwarding; verify the "correction approved and applied once", "different arguments are held" and "pre-approved special record released once" scenarios, and a restart test with the SQLite file
- [ ] 6.3 Add the issuer's JSON endpoints for the page: request view (summary, user code, current versus requested, lifetime, agent ID, the held call's arguments in plain words, the reason, level-4 marks), approver login from the one-time token (session cookie), and decision (approve, reject, narrow). Verify HTTP tests for the "opening the URL is not approving", "signed-in UI user who isn't the approver" and "approving less" scenarios
- [ ] 6.4 In `frontend/`, add `src/pages/approve/[id].astro` with `ApprovalRequest.svelte`, `src/pages/approve/login.astro`, and the proxy `src/pages/api/approve/[...path].ts` (relaying the HTTP-only, `SameSite=Strict` session cookie scoped to `/approve`); render the reason with text interpolation only. Verify with `npm run build`, a browser check that a request shows its summary, user code and literal `<b>URGENT</b>` reason ("agent's reason is not trusted text", "held correction shown in full", "approval URL opens the UI"), and that approving from the CLI login link works end to end
- [ ] 6.5 Set `FRONTEND_URL` for the issuer and the gateway so `approval_url` points at the UI; verify a created request's `approval_url` opens the page on `:8081`

## 7. Agent client and docs

- [ ] 7.1 Add `my_grants`, `check_access`, `request_scopes` and `await_approval` to the local MCP shim, with mandate switching on approval, and point it at a mandate issued with `--claims '{"clearance": 2}'` (the default mandate has no clearance and can't use `grants`); verify by hand in Claude Code that a refused `SCH02` roster leads to a request, a CLI approval and a successful retry
- [ ] 7.2 Write `docs/scope-requests.md` laid out like `questions/02-worked-example.md`. It starts by issuing a mandate with `clearance` and registering an approver key, then shows a refused call, the request result, the approval, the minted mandate decoded, the retried call, and what's unresolved. Verify each command runs on a fresh `make hack`
- [ ] 7.3 Document the new claims (`audience`, `parent`, `approved_by`, `preapproved`, `can_delegate`) and the tool grant in `gateway/lib/mandate.schema.json`; verify the file parses as JSON

## 8. Final checks

- [ ] 8.1 `make eval_run` gives 32/32 with `TOOL_GRANTS=enforce`, and question 0 at 12/12
- [ ] 8.2 `make test` passes, including the new gateway, issuer, grant and slices tests
- [ ] 8.3 `make lint` passes, and `npm run lint` and `npm run build` pass in `frontend/`
- [ ] 8.4 `docker compose up -d --build`, then a Day 2 dry run: a forged approval, a URL-only approval, a direct `:8080` call and a replayed tool grant are each refused, and `audit.events` shows the request, the approval and the retried call
