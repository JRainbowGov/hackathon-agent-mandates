-- Gateway store for the audit and history layers. Runs once, on an empty volume
-- (docker-entrypoint-initdb.d). Later changes go in numbered migrations; see docs/dev-scaffold.md.
--
-- Data rule: this store holds identifiers (pupil IDs, jti, agent_id) and PII *levels*, never data values.
-- Tool arguments are recorded as their keys plus a hash, never the values themselves.

CREATE SCHEMA IF NOT EXISTS gateway;
SET search_path = gateway, public;

CREATE TABLE schema_version (
    version    integer PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now(),
    note       text NOT NULL
);
INSERT INTO schema_version (version, note) VALUES (1, 'initial dev scaffold');

-- ---------------------------------------------------------------- audit trail (append-only, hash-chained)
-- event_hash = sha256 over the canonical JSON of the row (minus seq, event_hash, sig) including prev_hash.
-- The first row uses prev_hash = 'sha256:' || repeat('0', 64). UNIQUE(prev_hash) stops the chain forking:
-- each event can be extended exactly once. sig is the gateway's signature over event_hash.
CREATE TABLE audit_events (
    seq                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    decision_id        uuid        NOT NULL UNIQUE,
    ts                 timestamptz NOT NULL DEFAULT now(),
    -- mandate
    jti                text,                -- null when the mandate never verified
    agent_id           text,
    iss                text,
    principal          text,                -- the delegator
    parent_jti         text,                -- set for sub-delegated mandates
    -- request
    server             text        NOT NULL,
    tool               text        NOT NULL,
    arg_keys           text[]      NOT NULL DEFAULT '{}',
    arg_hash           text        NOT NULL, -- 'sha256:' || hex over canonical JSON of the arguments
    scope_urn          text,                 -- school URN the call was scoped to
    scope_pupil_id     text,                 -- pupil the call was scoped to, if any
    -- decision
    decision           text        NOT NULL CHECK (decision IN ('ALLOW', 'DENY', 'STEP_UP')),
    reason_code        text        NOT NULL,
    model_label        text,                 -- decision-model guardrail (may only tighten)
    model_confidence   real CHECK (model_confidence IS NULL OR model_confidence BETWEEN 0 AND 1),
    model_version      text,
    -- what came back (filled for ALLOW)
    rows_returned      integer CHECK (rows_returned IS NULL OR rows_returned >= 0),
    pupil_ids_returned text[]      NOT NULL DEFAULT '{}',
    max_pii_level      smallint CHECK (max_pii_level IS NULL OR max_pii_level BETWEEN 1 AND 4),
    -- chain
    prev_hash          text        NOT NULL UNIQUE,
    event_hash         text        NOT NULL UNIQUE,
    sig                text        NOT NULL
);
CREATE INDEX audit_events_jti_ts ON audit_events (jti, ts);
CREATE INDEX audit_events_agent_ts ON audit_events (agent_id, ts);
CREATE INDEX audit_events_pupils ON audit_events USING gin (pupil_ids_returned);

-- Belt and braces: the gateway role has no UPDATE/DELETE/TRUNCATE grant (02_gateway_role.sh),
-- and these triggers refuse them for every role, owner included, short of dropping the trigger.
CREATE FUNCTION audit_events_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only (% refused)', TG_OP;
END;
$$;
CREATE TRIGGER audit_events_no_update_delete
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_append_only();
CREATE TRIGGER audit_events_no_truncate
    BEFORE TRUNCATE ON audit_events
    FOR EACH STATEMENT EXECUTE FUNCTION audit_events_append_only();

-- ---------------------------------------------------------------- replay protection
-- Replaces Gateway._seen_nonces (in-memory, per process). INSERT ... ON CONFLICT DO NOTHING; zero rows = replay.
-- Rows can be pruned once expires_at (request ts + the 300s window) has passed.
CREATE TABLE nonces (
    nonce      text PRIMARY KEY,
    jti        text,
    seen_at    timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);
CREATE INDEX nonces_expires_at ON nonces (expires_at);

-- ---------------------------------------------------------------- throttling and budgets
-- One row per mandate, tool and window. Counters only; the limits themselves come from signed mandate claims.
CREATE TABLE budget_counters (
    jti          text        NOT NULL,
    tool         text        NOT NULL,
    window_start timestamptz NOT NULL,
    calls        integer     NOT NULL DEFAULT 0 CHECK (calls >= 0),
    rows         integer     NOT NULL DEFAULT 0 CHECK (rows >= 0),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (jti, tool, window_start)
);

-- Distinct pupils each mandate has seen; count(*) per jti is the "distinct pupils" budget.
CREATE TABLE mandate_pupils (
    jti           text        NOT NULL,
    pupil_id      text        NOT NULL,
    first_seen    timestamptz NOT NULL DEFAULT now(),
    max_pii_level smallint    NOT NULL CHECK (max_pii_level BETWEEN 1 AND 4),
    PRIMARY KEY (jti, pupil_id)
);

-- ---------------------------------------------------------------- gateway-owned suspensions
-- Separate from the issuer's status list: the issuer key never lives on the gateway, so the gateway
-- cannot revoke a mandate, only refuse to honour it. A row is active while lifted_at is null and
-- expires_at is null or in the future.
CREATE TABLE suspensions (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    subject_type text        NOT NULL CHECK (subject_type IN ('jti', 'agent_id', 'iss', 'principal')),
    subject      text        NOT NULL,
    reason_code  text        NOT NULL,
    note         text,
    created_by   text        NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz,
    lifted_at    timestamptz
);
CREATE INDEX suspensions_active ON suspensions (subject_type, subject) WHERE lifted_at IS NULL;
