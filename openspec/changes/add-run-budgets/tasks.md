## 1. Claims and audit store

- [ ] 1.1 Parse and validate `budget` and per-entry `rate` claims in `gateway/lib/budgets.py` (positive integers, optional fields), giving `BUDGET_INVALID`; verify unit tests for valid, missing and malformed claims, and that request arguments named `budget` are ignored
- [ ] 1.2 Add `family_jti` (parent.jti or own jti) and the matched scope-entry index to audit events and the SQLite schema, plus `pupils_for_family`, `allowed_calls_for_family` and `mandates_for_pupil_since` store queries in memory and SQLite; verify unit tests on both stores
- [ ] 1.3 Add the `alert` event type and `record_alert` with deterministic UUIDs for dedupe; verify a test that the same alert recorded twice is stored once and appears in `audit.events`

## 2. Checks in the request path

- [ ] 2.1 Add the unverified-source ceiling before `decide` and the per-key ceiling after it (`GATEWAY_UNVERIFIED_PER_MIN`, `GATEWAY_KEY_CEILING_PER_MIN`), giving `429 RATE_LIMITED` with `Retry-After` and throttled recording; verify the forged-flood scenario and that two back-to-back eval runs see no `RATE_LIMITED`
- [ ] 2.2 Add `rate.per_minute`, `rate.max_calls` and `budget.calls` checks before forwarding, with a per-family lock; verify the per-minute scenario and a lifetime-calls test that refused calls don't count
- [ ] 2.3 Add the distinct-pupil budget after forwarding and before recording: withhold the whole result with `429 BUDGET_EXHAUSTED`, record `DENY` with no pupils, and fail closed to `503 AUDIT_UNAVAILABLE` on any counting error; verify the one-at-a-time, crossing-the-budget, same-pupil-again and parent-shared scenarios
- [ ] 2.4 Add the three alert rules for claim-less mandates after recording; verify the eval-refusals and pupil-targeted scenarios, and that no claim-less decision changes

## 3. Docs and check-in

- [ ] 3.1 Document `budget` and `rate` in `gateway/lib/mandate.schema.json` and write `docs/run-budgets.md` like `questions/02-worked-example.md` (an Elmwood mandate with a pupil budget, a run of allowed calls, the call where it stops, `audit.saw` afterwards, what's unresolved); verify each command runs against the branch gateway

## 4. Final checks

- [ ] 4.1 `make eval_run` gives 32/32, question 0 at 12/12, run twice in a row against the same gateway
- [ ] 4.2 `make test` and `make lint` pass
- [ ] 4.3 `docker compose up -d --build gateway` on a fresh audit volume, then the Day 2 feature-mandate dry run: a one-at-a-time walk stops at the budget, and a forged flood gets `RATE_LIMITED` without crashing the gateway
