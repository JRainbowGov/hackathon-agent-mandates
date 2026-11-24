# Design

## Context

See proposal.md for why. How it works today:
- `Gateway.decide_with_context` (`gateway/lib/gateway_verify.py`) runs `check_request`. Only when the result is
  `STEP_UP` does it consult `_preapproved`, so an `ALLOW` under a release mandate never touches `preapproved`.
- The issuer mints release mandates in `mint_for` (`issuer/app.py`), with scope from `_held_union_scope`, pinned to
  `urn` and `pupil_id` only.
- The issuer's `create_request` validates the held list's shape and the person's ceiling. It doesn't check held calls
  against the requesting mandate.
- The step-up patterns are a default list inside `Gateway.__init__` (`["*.write", "*.draft", "special.*"]`). The
  `SPECIAL_CATEGORY` hold comes from `graded.special_category_read`, called inside `check_request`.

## Goals / Non-Goals

**Goals:**
- A release mandate can do nothing except its released calls, once each, whatever its scope says.
- The issuer, on its own, refuses held calls the parent mandate wouldn't hold.

**Non-Goals:**
- Narrowing the release mandate's minted scope further. The gateway rule makes it irrelevant, and the scope stays as
  a backstop for the server-side tool grant (urn and pupil subjects).

## Decisions

**1. Enforce at the gateway on the `preapproved` claim, not by minting a tighter scope.**
- **Where:** in `Gateway.decide_with_context`, right after `check_request`, replacing the current
  `STEP_UP`-only branch.
- **Order:** mandate, then proof of possession, then `check_request` (deny rules, clearance, scope, audience, row
  cap, step-up), then the release rule.
- **The rule:** if the claims carry a non-empty `preapproved`, the result is `ALLOW`/`PREAPPROVED` (marking the use)
  when `check_request` returned `ALLOW` or `STEP_UP` and the action hash is in the list and unused. Otherwise it is
  `DENY`/`NOT_RELEASED`. A `DENY` from `check_request` stands.
- **Alternative considered:** mint the release mandate with every argument pinned as a constraint. Rejected for
  three reasons:
  - constraints only check the keys they list, so an extra argument such as `limit` would still be free;
  - it does nothing for release mandates already minted;
  - it puts the rule in two places.

**2. `NOT_RELEASED` instead of holding again (`202`).**
- A release mandate has a `parent`, so `grants.request` refuses it, and a `202` under it can never be released.
  `403` says plainly that this mandate is the wrong one.
- The shim already retries on the base mandate after any non-200, so agents using it see the same `202` as today.

**3. The issuer re-runs the gateway's decision on each held call.**
- **Where:** in `create_request`, after `_held_list` and before the ceiling check.
- **The check:** build a hypothetical `Request` for each held call and run `check_request` with the requesting
  mandate's verified claims and the same step-up patterns. Require `STEP_UP`.
- **Shared patterns:** move the default patterns to a module constant (`STEP_UP_PATTERNS`) in `gateway_verify.py`,
  used by `Gateway` and the issuer, so the two can't drift.
- **Alternative considered:** have the gateway sign an attestation that a decision was held. That's stronger but
  needs a new token type and key use, so it's left as a follow-up (proposal Non-goals).

**Failure mode:** fail closed. An unexpected error in the release rule falls through to the existing catch-all
(`MANDATE_MALFORMED` DENY). An error checking a held call at the issuer refuses the request.

**Day 2 (ATTACK_SCORING.md):** closes data-flag levels 2 and 3 through a released held call on a gateway whose
feature is the escalation flow: names, deprivation and census rows from files outside the mandate. Opens nothing new.
A `NOT_RELEASED` refusal is a normal audited `DENY`.

## Risks / Trade-offs

- **An agent that retries a released call with changed arguments now gets `403` instead of `202`.** Mitigation: the
  reason code is specific, and the shim falls back to the base mandate, which holds it for a new approval.
- **The issuer evaluating `check_request` needs the same environment as the gateway** (`GATEWAY_CLAIMLESS_LEVEL`,
  audience data). Mitigation: held calls only reach `STEP_UP` through clearance-4 or pattern rules, which don't
  depend on that environment. A test covers both the issuer and gateway paths with the same fixtures.

## Migration Plan

Rebuild the gateway and issuer containers. Release mandates in flight (five minutes at most) pick up the rule at
once. Roll back by redeploying the previous images; no state changes.
