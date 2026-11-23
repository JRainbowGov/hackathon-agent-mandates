#!/bin/sh
# Creates the least-privilege role the gateway connects as. Runs once, after 01_schema.sql, on an empty volume.
# POSTGRES_USER owns the schema; the gateway role is neither owner nor superuser, so the REVOKEs below hold.
set -eu

: "${GATEWAY_DB_USER:?set GATEWAY_DB_USER in .env (see .env.example)}"
: "${GATEWAY_DB_PASSWORD:?set GATEWAY_DB_PASSWORD in .env (see .env.example)}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v gw_user="$GATEWAY_DB_USER" -v gw_pass="$GATEWAY_DB_PASSWORD" <<'SQL'
CREATE ROLE :"gw_user" LOGIN PASSWORD :'gw_pass' NOSUPERUSER NOCREATEDB NOCREATEROLE;
ALTER ROLE :"gw_user" SET search_path = gateway;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA gateway TO :"gw_user";

-- audit trail: read and append, nothing else
REVOKE ALL ON gateway.audit_events FROM :"gw_user";
GRANT SELECT, INSERT ON gateway.audit_events TO :"gw_user";
REVOKE UPDATE, DELETE, TRUNCATE ON gateway.audit_events FROM :"gw_user";

-- working state the gateway maintains
GRANT SELECT, INSERT, DELETE ON gateway.nonces TO :"gw_user";
GRANT SELECT, INSERT, UPDATE, DELETE ON gateway.budget_counters TO :"gw_user";
GRANT SELECT, INSERT ON gateway.mandate_pupils TO :"gw_user";
GRANT SELECT, INSERT, UPDATE ON gateway.suspensions TO :"gw_user";
GRANT SELECT ON gateway.schema_version TO :"gw_user";
GRANT USAGE ON ALL SEQUENCES IN SCHEMA gateway TO :"gw_user";
SQL
