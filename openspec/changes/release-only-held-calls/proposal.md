# Proposal

## Why

Approving a held call is meant to let that one call through once. It actually grants a five-minute scope. The minted
mandate's scope is the held call's server and tool, pinned only to its `urn` and `pupil_id`, and the one-use rule
(`preapproved`) only matters for calls that would be held again. Every other call of that tool is simply allowed.

Red-teaming on 24 Nov showed this through the gateway, with every step taken as intended:
- **The mandate:** clearance 4, allowed to `get` the census file only.
- **The hold:** the census read was held (`SPECIAL_CATEGORY`), and the person approved "Release one held call: Read
  data files (path=…census.csv)".
- **What it unlocked:** the minted mandate's scope was `pupil-data.get` with no constraints. For five minutes it read
  `display_names.csv` and `deprivation.csv`, which the base mandate refused.

A second gap makes this worse off the gateway. The issuer creates a held-call request without checking that the call
was ever held, or that the requesting mandate covers it at all. Only the gateway checks that. An agent that reaches
the issuer's internal route (`127.0.0.1:8083`, loopback on the host) can name a made-up held call. The test used a
Brookmere search from a Dunmore roster mandate, and the issuer accepted it.

Questions **9** (step-up) and **7** (delegation). Layer: scope requests, the held-call path.

## What Changes

- **A release mandate allows only its released calls.** A mandate with a `preapproved` claim allows a call only when
  its action hash is in `preapproved` and not yet used. Anything else under that mandate is refused with a new
  reason, `403 NOT_RELEASED`, even a call its scope would otherwise allow.
- **BREAKING (for callers holding a release mandate):** a repeated released call, or one that wasn't released, used
  to come back as `202` held again. It now gets `403 NOT_RELEASED`. A release mandate can't ask for anything (it has
  a `parent`), so that `202` was a dead end. The shim already falls back to the base mandate on any non-200, where
  the call is held as before.
- **The issuer checks held calls against the requesting mandate.** It creates a held-call request only if every
  named call is one the requesting mandate's own claims would hold (`STEP_UP`). Anything else is refused with a new
  reason, `403 HELD_OUTSIDE_MANDATE`, and no request is created.
- **Applies to release mandates already minted.** The gateway reads the `preapproved` claim, so a release mandate
  minted before this change gets the new rule too.

Mandates without `preapproved` (every base mandate, every scope-request approval, the eval pack) are unaffected.
Question 0 keeps passing.

## Capabilities

### New Capabilities
- `held-release`: what a mandate minted to release held calls may do, and which held calls the issuer will put in
  front of a person.

### Modified Capabilities
None in main specs. `scope-requests` (add-scope-requests) and `batch-release` (add-batch-release) are still pending
changes. This change replaces their "held again" outcome for repeats with `NOT_RELEASED`, and updates those
scenarios to match.

## Non-goals

- **Proving at the issuer that a call really was held.** The issuer can't read the gateway's audit trail. It checks
  that the parent mandate would hold the call, which stops calls outside the mandate. It doesn't stop an agent naming
  an in-scope held call it never made. The gateway's audit check still covers that on the normal path. A signed
  "held" attestation from the gateway is a follow-up.
- **Changing which calls are held.**
- **Locking the issuer's internal routes to the gateway** (network or mTLS). The deploy setup already keeps them on
  loopback.

## Impact

- **Changed code:**
  - `gateway/lib/gateway_verify.py`: the release-mandate rule, in `Gateway.decide_with_context`.
  - `issuer/app.py`: the held-call check in `create_request`.
  - The step-up patterns, shared so the issuer applies the same list as the gateway.
- **Tests:**
  - `gateway/tests/test_scope_requests.py`: the repeat scenarios become `403 NOT_RELEASED`, plus new cases.
  - `gateway/tests/test_shim.py`: unchanged. The shim's fallback still shows `202`.
- **Docs:** `docs/scope-requests.md` ("Held calls go through once").
- **Day 2:** closes the "one approval, five minutes of every file" path on a gateway whose feature is the escalation
  flow.
