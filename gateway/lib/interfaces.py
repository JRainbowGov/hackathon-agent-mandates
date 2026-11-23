"""Data levels of the servers behind the gateway, and the mandate clearance check (OpenSpec add-interface-slices).

Each server serves one class of data, on the manifest's scale: 1 public, 2 basic PII, 3 sensitive PII,
4 special category. A mandate's top-level `clearance` claim is the highest level it may call. The levels are
gateway policy: they never come from the request, the mandate or the server.
"""
from __future__ import annotations

SERVER_LEVELS: dict[str, int] = {
    "pupil-data": 4,  # the starter server can return special category columns
    "schools": 1,
    "directory": 2,
    "grants": 1,  # answered by the gateway itself (gateway/lib/grants.py); the caller's own grants, no pupil data
    "audit": 2,  # answered by the gateway itself (gateway/lib/audit.py); returns pupil IDs, no other pupil data
    "special": 4,
}

# Servers that keep today's decisions for mandates without a clearance claim (the eval, Day 2's default mandate).
LEGACY_SERVERS = frozenset({"pupil-data"})
# ...but what such a mandate is sent stops here: special category columns (ethnicity, care status) need an
# explicit clearance of 4. Applied in the tool grant, so the server drops those columns from every row.
LEGACY_LEVEL = 3


def check_clearance(server: str, claims: dict) -> tuple[str, str, str] | None:
    """A DENY (decision, reason_code, detail), or None when the clearance allows this server.

    `claims` must be the verified mandate claims: clearance is never read from the request.
    """
    level = SERVER_LEVELS.get(server)
    if level is None:
        return "DENY", "UNKNOWN_SERVER", server
    if "clearance" not in claims:
        if server in LEGACY_SERVERS:
            return None
        return "DENY", "CLEARANCE_MISSING", f"{server} is level {level}; the mandate has no clearance"
    clearance = claims["clearance"]
    # bool is a subclass of int, so `true` would otherwise pass as clearance 1
    if type(clearance) is not int or not 1 <= clearance <= 4:
        return "DENY", "CLEARANCE_INVALID", repr(clearance)
    if level > clearance:
        return "DENY", "CLEARANCE_TOO_LOW", f"{server} is level {level}, clearance is {clearance}"
    return None
