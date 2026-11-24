# Tasks

## 1. A release mandate allows only its released calls

- [x] 1.1 In `gateway/lib/gateway_verify.py`, move the default step-up patterns to a module constant `STEP_UP_PATTERNS` and use it in `Gateway.__init__`; verify `uv run python -m pytest gateway/tests` still passes
- [x] 1.2 Add the release rule to `Gateway.decide_with_context` (design decision 1): `PREAPPROVED` for an unused listed hash on `ALLOW` or `STEP_UP`, `NOT_RELEASED` for any other non-DENY under a non-empty `preapproved`; the five scenarios are covered through `/tools/call` in `test_scope_requests.py` (released once, another file, repeat, kept refusal, base mandate unchanged)
- [x] 1.3 Add an end-to-end test in `gateway/tests/test_scope_requests.py` reproducing the 24 Nov finding: clearance-4 census-only mandate, held census `get`, person approves, then `get` of `display_names.csv` with the minted mandate returns `403 NOT_RELEASED`; verify it fails before 1.2 and passes after
- [x] 1.4 Update the existing repeat assertions in `gateway/tests/test_scope_requests.py` (the `SENSITIVE_TOOL` / `SPECIAL_CATEGORY` repeats under a minted mandate) to `403 NOT_RELEASED`; verify `gateway/tests/test_shim.py` passes unchanged, since the shim falls back to the base mandate
- [x] 1.5 Update `docs/scope-requests.md` "Held calls go through once" and the repeat scenarios in `openspec/changes/add-scope-requests/specs/scope-requests/spec.md` and `openspec/changes/add-batch-release/specs/batch-release/spec.md` to say `NOT_RELEASED`; verify `openspec validate --all` passes

## 2. The issuer releases only calls the requesting mandate would hold

- [x] 2.1 In `issuer/app.py` `create_request`, run `check_request` with the requesting mandate's claims and `STEP_UP_PATTERNS` on each held call and refuse with `403 HELD_OUTSIDE_MANDATE` unless it is `STEP_UP`; verify with tests posting straight to the issuer app (made-up Brookmere search from a Dunmore roster mandate, and a held `get` of an allowed-outright file) that no request is created
- [x] 2.2 Check that the gateway passes `HELD_OUTSIDE_MANDATE` through as the `grants.request` decision (it passes every issuer refusal code through unchanged; through the gateway a made-up call is refused earlier, by the audit check, with `REQUEST_INVALID`), and that the genuinely held census call still creates a pending request (`test_a_released_read_opens_no_other_file`)
- [x] 2.3 Add `HELD_OUTSIDE_MANDATE` and `NOT_RELEASED` to the reason codes listed in `docs/scope-requests.md` (written into "Held calls go through once"; the live run is 3.4)

## 3. Integration

- [ ] 3.1 (not run: another session owns the running stack) `make eval_run`: question 0 at 12/12 and no regressions in 1 to 5
- [x] 3.2 `make test`
- [x] 3.3 `make lint`
- [ ] 3.4 (not run: another session owns the running stack) `docker compose up -d --build gateway issuer`, then repeat the 24 Nov steps (proposal, Why) against `:8082` with the CLI: the census read is released once, and `display_names.csv` under the minted mandate returns `403 NOT_RELEASED`
