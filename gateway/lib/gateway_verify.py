"""Gateway verification pipeline.

    receive (request, mandate)
      -> verify mandate: issuer accredited / signature / time / revocation
      -> verify proof of possession (request signed by cnf key, fresh nonce and ts)
      -> check request against scope, deny and constraints
      -> decision record {ALLOW | DENY | STEP_UP, reason_code, ...}

Reason codes are stable strings so the audit log and Day 2 scorecard can
count them. Order of checks is deliberate: cheapest and most definitive first.
"""

from __future__ import annotations

import fnmatch
import logging
import posixpath
import time
from dataclasses import asdict, dataclass, field

import jwt

from .common import canonical, jwk_thumbprint, jwk_to_pub, pub_to_pem, sha256_hex, verify_bytes
from .interfaces import check_clearance
from .status_list import is_revoked

POLICY_VERSION = "2026-11-18.1"
CLOCK_SKEW = 30
# Most rows one call may ask for (the MCP server's own default).
# shortcut: per call only, many small calls still add up (question 11); add a per-mandate budget for that
MAX_ROWS = 100
# scope-constrained arguments the audit trail may record by value: they say whose data a call concerned
AUDITED_SCOPE_KEYS = ("urn", "pupil_id")

log = logging.getLogger(__name__)


class Reject(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


@dataclass
class Decision:
    decision: str  # ALLOW | DENY | STEP_UP
    reason_code: str
    policy_version: str
    mandate_hash: str
    request_hash: str
    agent_id: str | None
    ts: float
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AuditContext:
    """What the audit trail needs about a call beyond the Decision. Never returned to the caller.

    `claims` is set only when the mandate and the request signature both verified (identity_verified). Before
    that, `claimed_jti` / `claimed_iss` hold whatever the mandate says, read without trusting it.
    """

    identity_verified: bool = False
    claims: dict | None = None
    kid: str | None = None
    claimed_jti: str | None = None
    claimed_iss: str | None = None
    scope_values: dict[str, str] = field(default_factory=dict)


def _claimed_identity(token: str) -> tuple[str | None, str | None, str | None]:
    """(jti, iss, kid) as the mandate states them, unverified; Nones when it doesn't parse."""
    try:
        hdr = jwt.get_unverified_header(token)
        payload = jwt.decode(token, options={"verify_signature": False})
    except Exception:  # noqa: BLE001  (anything unparseable just has no claimed identity)
        return None, None, None
    as_str = lambda v: v if isinstance(v, str) else None  # noqa: E731
    return as_str(payload.get("jti")), as_str(payload.get("iss")), as_str(hdr.get("kid"))


def _scope_values(req: Request, scope: list[dict]) -> dict[str, str]:
    """Values of the audited keys that some scope entry for this server and tool constrains."""
    constrained = {
        k
        for entry in scope
        if entry.get("server") == req.server and req.tool in entry.get("tools", [])
        for k in entry.get("constraints", {})
    }
    return {k: str(req.arguments[k]) for k in AUDITED_SCOPE_KEYS if k in constrained and k in req.arguments}


@dataclass
class Request:
    """What the agent sends to the gateway for a tools/call."""

    server: str
    tool: str
    arguments: dict
    mandate: str  # compact JWT
    nonce: str
    ts: int
    sig: str  # Ed25519 over canonical(signing_input()) by cnf key

    def signing_input(self) -> bytes:
        return canonical(
            {
                "server": self.server,
                "tool": self.tool,
                "arguments": self.arguments,
                "mandate_hash": sha256_hex(self.mandate.encode()),
                "nonce": self.nonce,
                "ts": self.ts,
            }
        )


# ---------------------------------------------------------------- mandate


def verify_mandate(token: str, registry, status_lists: dict[str, str]) -> dict:
    """Returns the verified claims. Raises Reject."""
    hdr = jwt.get_unverified_header(token)
    if hdr.get("typ") != "mandate+jwt":
        raise Reject("WRONG_TOKEN_TYPE", hdr.get("typ"))
    unverified = jwt.decode(token, options={"verify_signature": False})

    pub = registry.issuer_key(unverified["iss"], hdr.get("kid", ""))
    if pub is None:
        raise Reject("ISSUER_NOT_ACCREDITED", unverified["iss"])
    try:
        claims = jwt.decode(
            token,
            pub_to_pem(pub),
            algorithms=["EdDSA"],
            options={"verify_exp": False, "verify_nbf": False, "require": ["exp", "iss", "jti"]},
        )
    except jwt.PyJWTError as e:
        raise Reject("SIG_INVALID", str(e))

    now = time.time()
    if claims.get("nbf", 0) > now + CLOCK_SKEW:
        raise Reject("NOT_YET_VALID", claims["jti"])
    if claims["exp"] < now - CLOCK_SKEW:
        raise Reject("EXPIRED", claims["jti"])

    sl = claims["status"]["status_list"]
    sl_jwt = status_lists.get(sl["uri"])
    if sl_jwt is None:
        raise Reject("STATUS_UNAVAILABLE", sl["uri"])  # fail closed
    try:
        if is_revoked(sl_jwt, sl["idx"], pub, sl["uri"]):
            raise Reject("REVOKED", claims["jti"])
    except ValueError as e:
        raise Reject("STATUS_UNAVAILABLE", str(e))
    return claims


# ---------------------------------------------------------------- scope


def check_request(
    req: Request, scope: list[dict], deny: list[str], step_up_patterns: list[str], claims: dict
) -> tuple[str, str, str]:
    name = f"{req.server}.{req.tool}"
    for pat in deny:
        if fnmatch.fnmatch(name, pat):
            return "DENY", "DENIED_BY_RULE", pat
    # clearance before scope, so no shape of scope entries can route around it
    if refused := check_clearance(req.server, claims):
        return refused
    # Each entry is a whole grant: the call is allowed if any one entry accepts every argument it constrains,
    # so a request cannot take urn from one entry and path from another.
    refused = None  # the first matching entry's reason, reported when no entry accepts the call
    for entry in scope:
        if entry["server"] != req.server or req.tool not in entry["tools"]:
            continue
        for k, allowed in entry.get("constraints", {}).items():
            if k not in req.arguments:
                refused = refused or ("DENY", "CONSTRAINT_MISSING", k)
                break
            value = req.arguments[k]
            if k == "path" and isinstance(value, str):
                # one file, one spelling: "./a//b" and "a/x/../b" compare as "a/b". Anything still starting
                # with ".." or "/" cannot equal an allowed relative path, so it stays denied.
                # shortcut: lexical only, agrees with the MCP server's resolve() while the data dir has no symlinks
                value = posixpath.normpath(value)
            if str(value) not in set(map(str, allowed)):
                refused = refused or ("DENY", "CONSTRAINT_VIOLATED", f"{k}={req.arguments[k]!r}")
                break
        else:
            limit = req.arguments.get("limit", MAX_ROWS)
            if type(limit) is not int or not 0 <= limit <= MAX_ROWS:
                return "DENY", "TOO_MUCH", f"limit={limit!r}, at most {MAX_ROWS}"
            if req.tool == "search" and not str(req.arguments.get("query", "")).strip():
                return "DENY", "TOO_MUCH", "empty query matches every row"
            for pat in step_up_patterns:
                if fnmatch.fnmatch(name, pat):
                    return "STEP_UP", "SENSITIVE_TOOL", pat
            return "ALLOW", "IN_SCOPE", ""
    return refused or ("DENY", "OUT_OF_SCOPE", name)


# ---------------------------------------------------------------- the pipeline


class Gateway:
    def __init__(self, registry, status_lists: dict[str, str], step_up_patterns: list[str] | None = None):
        self.registry = registry
        self.status_lists = status_lists
        self.step_up = step_up_patterns or ["*.write", "*.draft", "special.*"]
        self._seen_nonces: set[str] = set()

    def decide(self, req: Request) -> Decision:
        return self.decide_with_context(req)[0]

    def decide_with_context(self, req: Request) -> tuple[Decision, AuditContext]:
        base = dict(
            policy_version=POLICY_VERSION,
            mandate_hash=sha256_hex(req.mandate.encode()),
            request_hash=sha256_hex(req.signing_input()),
            ts=time.time(),
        )
        ctx = AuditContext()
        try:
            claims = verify_mandate(req.mandate, self.registry, self.status_lists)
            jwk = claims["cnf"]["jwk"]
            if abs(req.ts - time.time()) > 300:
                raise Reject("POP_FAILED", "request timestamp outside window")
            if req.nonce in self._seen_nonces:
                raise Reject("POP_FAILED", "replayed nonce")
            if not verify_bytes(jwk_to_pub(jwk), req.signing_input(), req.sig):
                raise Reject("POP_FAILED", f"bad signature for jkt {jwk_thumbprint(jwk)}")
            self._seen_nonces.add(req.nonce)
            ctx.identity_verified, ctx.claims = True, claims
            ctx.kid = jwt.get_unverified_header(req.mandate).get("kid")  # header was checked with the signature

            ctx.scope_values = _scope_values(req, claims["scope"])
            decision, code, detail = check_request(req, claims["scope"], claims["deny"], self.step_up, claims)
            return Decision(decision, code, agent_id=claims["agent_id"], detail=detail, **base), ctx
        except Reject as r:
            result = Decision("DENY", r.code, agent_id=None, detail=r.detail, **base)
        except Exception:  # anything else (an unparseable mandate, a malformed claim) fails closed, never a 500
            log.warning("unexpected error deciding a call", exc_info=True)
            result = Decision("DENY", "MANDATE_MALFORMED", agent_id=None, **base)
        if not ctx.identity_verified:
            ctx.claims = None
            ctx.claimed_jti, ctx.claimed_iss, ctx.kid = _claimed_identity(req.mandate)
        return result, ctx
