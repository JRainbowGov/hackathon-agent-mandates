"""HTTP wrapper around the gateway pipeline.

POST /tools/call  {server, tool, arguments, mandate, nonce, ts, sig}
  -> verify mandate + proof of possession (gateway/lib/gateway_verify.py)
  -> ALLOW: forward to the MCP server, DENY: 403, STEP_UP: 202
"""

import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from fastmcp import Client
from fastmcp.exceptions import ToolError
from pydantic import BaseModel

from gateway.cli import sign_request
from gateway.lib import audit
from gateway.lib.common import generate_keypair, pub_to_jwk
from gateway.lib.gateway_verify import Gateway, Request
from gateway.lib.interfaces import SERVER_LEVELS
from gateway.lib.status_list import is_revoked
from gateway.lib.trust_registry import TrustedList

log = logging.getLogger(__name__)
# answered by the gateway itself, never forwarded (gateway/lib/audit.py)
AUDIT_SERVER = "audit"
AUDIT_TOOLS = {
    "events": "The request log for a principal or a jti: who called, when, from where, what, and the decision.",
    "saw": "What a mandate (jti) received: pupils, columns, highest PII level, call counts, in plain words.",
}

STATE_DIR = Path(os.environ.get("GATEWAY_STATE_DIR", "gateway/state"))
# name -> URL (or an in-process FastMCP instance in tests); fastmcp.Client accepts both
MCP_SERVERS: dict[str, object] = dict(
    kv.split("=", 1) for kv in os.environ.get("MCP_SERVERS", "pupil-data=http://backend:8080/mcp/").split(",")
)
state: dict = {}


class CallBody(BaseModel):
    server: str
    tool: str
    arguments: dict
    mandate: str
    nonce: str
    ts: int
    sig: str


def load_state(state_dir: Path) -> None:
    registry = TrustedList(json.loads((state_dir / "trusted_list.json").read_text()))
    # shortcut: nonce replay set lives in Gateway._seen_nonces, in-memory per process; share it before multi-replica
    state["gateway"] = Gateway(registry, status_lists={})
    state["status_uri"] = json.loads((state_dir / "status_list.json").read_text())["uri"]
    state["dir"] = state_dir


@asynccontextmanager
async def lifespan(_app: FastAPI):
    load_state(STATE_DIR)
    audit.init_store(STATE_DIR)  # SQLite file when GATEWAY_AUDIT_DB is set, in memory otherwise
    yield


app = FastAPI(title="mandate gateway", lifespan=lifespan)


@app.get("/healthcheck")
def healthcheck() -> dict:
    return {"status": "ok"}


@app.get("/describe")
async def describe() -> dict:
    """Discovery for bring-your-own agents: what can be called and how a request must be signed."""
    servers = {}
    for name, target in MCP_SERVERS.items():
        async with Client(target) as client:
            servers[name] = [
                {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in await client.list_tools()
            ]
    servers[AUDIT_SERVER] = [{"name": n, "description": d} for n, d in AUDIT_TOOLS.items()]
    priv, pub = generate_keypair()
    example = sign_request(
        priv,
        server="pupil-data",
        tool="search",
        arguments={"query": "P0004", "urn": "SCH01"},
        mandate="<compact mandate JWT>",
    )
    return {
        "servers": servers,
        # data level per server (1 public .. 4 special category); a mandate's clearance must cover it
        "server_levels": {name: SERVER_LEVELS.get(name) for name in servers},
        "step_up_patterns": state["gateway"].step_up,
        "signing": {
            "alg": "Ed25519 by the key in the mandate's cnf.jwk; sig is base64url without padding",
            "signing_input": "canonical JSON (sorted keys, separators ',' and ':', ensure_ascii=False) of "
            "{server, tool, arguments, mandate_hash, nonce, ts}",
            "mandate_hash": "'sha256:' + hex sha256 of the compact mandate JWT",
            "ts": "unix seconds, within 300s of gateway time; nonce must be unique per request",
            "example": {
                "agent_jwk": pub_to_jwk(pub),
                "signing_input": Request(**example).signing_input().decode(),
                "request": example,
            },
        },
    }


def _source_addr(http: HTTPRequest | None) -> str | None:
    """The caller's address. X-Forwarded-For counts only when the immediate peer is the trusted proxy."""
    if http is None:
        return None
    peer = http.client.host if http.client else None
    trusted = os.environ.get("GATEWAY_TRUSTED_PROXY")
    forwarded = http.headers.get("x-forwarded-for")
    if trusted and peer == trusted and forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return peer


def _mandate_revoked(event: dict) -> bool | None:
    """Whether the mandate behind an audit event is revoked now, from its issuer's signed status list."""
    gateway: Gateway = state["gateway"]
    pub = gateway.registry.issuer_key(event["iss"] or "", event["issuer_kid"] or "")
    sl_jwt = gateway.status_lists.get(state["status_uri"])
    if pub is None or sl_jwt is None or event["status_idx"] is None:
        return None
    try:
        return is_revoked(sl_jwt, event["status_idx"], pub, state["status_uri"])
    except ValueError:
        return None


async def _forward(body: CallBody):
    """(http_status, result data or None, error text or None) for an allowed call."""
    if body.server == AUDIT_SERVER:
        try:
            return 200, await audit.handle(body.tool, body.arguments, _mandate_revoked), None
        except ValueError as e:
            return 400, None, str(e)
    target = MCP_SERVERS.get(body.server)
    if target is None:
        return 404, None, f"no MCP server configured for {body.server!r}"
    try:
        async with Client(target) as client:
            result = await client.call_tool(body.tool, body.arguments)
    except ToolError as e:
        return 502, None, str(e)
    return 200, result.data, None


@app.post("/tools/call")
async def tools_call(body: CallBody, http: HTTPRequest = None):  # None when called in-process (demo)
    gateway: Gateway = state["gateway"]
    # re-read the published status list each request so `cli revoke` applies without a restart
    gateway.status_lists[state["status_uri"]] = (state["dir"] / "status_list.jwt").read_text().strip()

    decision, ctx = gateway.decide_with_context(Request(**body.model_dump()))
    record = {**decision.to_dict(), "decision_id": str(uuid.uuid4())}

    if decision.decision == "ALLOW":
        status, data, error = await _forward(body)
    else:
        status, data, error = (403 if decision.decision == "DENY" else 202), None, None
    summary = audit.summarise(data, body.server) if status == HTTPStatus.OK else None

    try:
        await audit.record(
            decision=record,
            ctx=ctx,
            server=body.server,
            tool=body.tool,
            arguments=body.arguments,
            source_addr=_source_addr(http),
            http_status=status,
            summary=summary,
        )
    except audit.AuditUnavailable:
        log.exception("audit event not written for decision %s", record["decision_id"])
        if status == HTTPStatus.OK:  # nothing leaves the gateway without its record
            withheld = {**record, "decision": "DENY", "reason_code": "AUDIT_UNAVAILABLE", "detail": ""}
            return JSONResponse({"decision": withheld}, status_code=503)

    if status == HTTPStatus.NOT_FOUND:
        raise HTTPException(404, error)
    if error is not None:
        return JSONResponse({"decision": record, "error": error}, status_code=status)
    if status != HTTPStatus.OK:
        return JSONResponse({"decision": record}, status_code=status)
    return {"decision": record, "result": data}


class ExternalEventBody(BaseModel):
    token: str  # an audit-event+jwt signed by a trusted issuer (audit.sign_external_event)


@app.post("/internal/audit-events")
async def internal_audit_event(body: ExternalEventBody):
    """Approval events from the issuer service, added to the audit chain.

    The issuer's signature is the only gate: anyone may call this, but only an event signed by an issuer on the
    trusted list is recorded. The same event (its jti) sent again is acknowledged without a second record.
    """
    try:
        stored, new = await audit.record_signed_external(body.token, state["gateway"].registry)
    except audit.ExternalEventRejected as e:
        status = HTTPStatus.BAD_REQUEST if e.code in ("EVENT_INVALID", "EVENT_REJECTED") else HTTPStatus.FORBIDDEN
        return JSONResponse({"recorded": False, "reason_code": e.code, "detail": e.detail}, status_code=status)
    except audit.AuditUnavailable:
        log.exception("issuer event not written")
        return JSONResponse({"recorded": False, "reason_code": "AUDIT_UNAVAILABLE"}, status_code=503)
    payload = {"recorded": True, "duplicate": not new, "decision_id": stored["decision_id"], "seq": stored["seq"]}
    return JSONResponse(payload, status_code=HTTPStatus.CREATED if new else HTTPStatus.OK)


@app.get("/healthcheck/audit")
def healthcheck_audit() -> dict:
    """Which audit store is in use and whether it survives a restart. No paths, no events."""
    return audit.store_status()


@app.get("/audit/head")
async def audit_head() -> dict:
    """The latest audit event's seq, hash and gateway signature, for anchoring outside the gateway. No data."""
    return await audit.head()


from gateway.demo import router as demo_router  # noqa: E402  (demo imports main lazily)

app.include_router(demo_router)
