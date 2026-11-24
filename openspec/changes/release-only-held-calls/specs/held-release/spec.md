# Spec Delta

## Purpose

Makes approving a held call release exactly that call, once. The mandate minted for it grants nothing else, and the
issuer only asks a person to release calls the requesting mandate would itself have held.

## ADDED Requirements

### Requirement: A release mandate allows only its released calls
Given a mandate with a `preapproved` claim, the gateway SHALL allow a call only if all of these hold:
- the call's action hash is in `preapproved`;
- the gateway has no record of using it;
- every other check allows or would hold the call.

Such a call SHALL return `200 ALLOW` with reason `PREAPPROVED`. Any other call that every other check allows or
would hold SHALL return `403 DENY` with reason `NOT_RELEASED`. A call another check refuses keeps that refusal.

#### Scenario: The released call goes through
- **GIVEN** a clearance-4 mandate allowing `pupil-data.get` with `path=["synthetic/synthetic_personal_data_school_census.csv"]`, whose `get` of that file was held with `202 SPECIAL_CATEGORY` and released by the person
- **WHEN** the agent makes the same `get` with the minted mandate
- **THEN** the gateway returns `200 ALLOW` with reason `PREAPPROVED`

#### Scenario: Another file under the release mandate
- **GIVEN** the same minted mandate, whose scope allows `pupil-data.get` with no path constraint
- **WHEN** the agent calls `pupil-data.get` with `path="synthetic/synthetic_display_names.csv"`
- **THEN** the gateway returns `403 DENY` with reason `NOT_RELEASED`, and no data is returned

#### Scenario: The released call made twice
- **GIVEN** the released `get` already went through once with the minted mandate
- **WHEN** the agent makes it again with the minted mandate
- **THEN** the gateway returns `403 DENY` with reason `NOT_RELEASED`

#### Scenario: A refusal from another check is kept
- **GIVEN** a release mandate whose `deny` includes `*.write`
- **WHEN** the agent calls `pupil-data.write` with it
- **THEN** the gateway returns `403 DENY` with reason `DENIED_BY_RULE`, not `NOT_RELEASED`

#### Scenario: The base mandate is unchanged
- **GIVEN** the base mandate the release was asked from
- **WHEN** the agent makes the released `get` again with the base mandate
- **THEN** the gateway returns `202 STEP_UP` with reason `SPECIAL_CATEGORY`, as before

### Requirement: Mandates without preapproved are unaffected
A mandate with no `preapproved` claim, or an empty one, SHALL be decided exactly as before this change.

#### Scenario: A scope-request approval
- **GIVEN** a mandate minted by approving a scope request for `directory.roster` at `SCH02` (no `preapproved` claim)
- **WHEN** the agent calls `directory.roster` with `urn="SCH02"` several times
- **THEN** each call returns `200 ALLOW` with reason `IN_SCOPE`

### Requirement: The issuer releases only calls the requesting mandate would hold
The issuer SHALL create a held-call request only if each named call, checked against the requesting mandate's
verified claims, would be held (`STEP_UP`). Otherwise it SHALL refuse with `403 HELD_OUTSIDE_MANDATE`, create no
request, and the gateway SHALL return that reason to the agent.

#### Scenario: A made-up call outside the mandate, sent straight to the issuer
- **GIVEN** a clearance-2 mandate allowing only `directory.roster` at `SCH04`
- **WHEN** a signed `grants.request` naming a held `pupil-data.search` with `urn="SCH02"` and `query="a"` is posted to the issuer's internal route, bypassing the gateway
- **THEN** the issuer refuses with `403 HELD_OUTSIDE_MANDATE`, and no request or approval page exists

#### Scenario: A call the mandate allows without holding
- **GIVEN** a clearance-4 mandate allowing `pupil-data.get` at any path
- **WHEN** a request names a held `get` of `synthetic/synthetic_schools.csv`, which that mandate allows outright
- **THEN** the issuer refuses with `403 HELD_OUTSIDE_MANDATE`

#### Scenario: A genuinely held call
- **GIVEN** the clearance-4 census-only mandate and its held census `get`
- **WHEN** the agent asks through the gateway with `grants.request` and `held` naming that call
- **THEN** a pending request is created, as before
