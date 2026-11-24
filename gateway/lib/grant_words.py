"""Plain words for grants, generated from the structured scope (OpenSpec add-scope-requests).

Whatever a person reads before approving comes from here, never from the agent's own text, so the description
matches what will be enforced. Used by the gateway (grants.self) and the issuer (request summary, approval view).
"""

from __future__ import annotations

import csv
import os
import re
import time
from functools import lru_cache
from pathlib import Path

SCHOOLS_PATH = Path(
    os.environ.get(
        "GATEWAY_SCHOOLS_PATH",
        Path(__file__).resolve().parents[2] / "mcp_server/data/synthetic/synthetic_schools.csv",
    )
)

TOOL_WORDS = {
    ("pupil-data", "search"): "Search pupils' census records",
    ("pupil-data", "get"): "Read data files",
    ("pupil-data", "aggregate"): "Count pupils by group",
    ("pupil-data", "classification"): "Read the data sensitivity labels",
    ("pupil-data", "roster"): "List Year 10 and 11 pupils' IDs and names",
    ("pupil-data", "pupil"): "Read pupils' records",
    ("pupil-data", "draft"): "Draft letters home",
    ("pupil-data", "write"): "Correct pupils' census records",
    ("schools", "list"): "List schools",
    ("schools", "classification"): "Read the data sensitivity labels",
    ("directory", "roster"): "List Year 10 and 11 pupils' IDs and names",
    ("directory", "name"): "Look up pupils' names",
    ("special", "record"): "Read pupils' ethnicity and care status",
    ("audit", "events"): "Read the request log",
    ("audit", "saw"): "See what an agent received",
}
LEVEL_4_SERVERS = {"special"}  # always level 4; pupil-data only at clearance 4 (graded)
# graded pupil-data (add-graded-pupil-data): what a read returns at each clearance, so the words never say more or less
GRADED_SERVER = "pupil-data"
GRADED_TOOLS = {"search", "pupil"}
GRADED_WORDS = {
    1: "with school and term only, no pupil details",
    2: "with basic details only, not free school meals, language, ethnicity or care status",
    3: "including free school meals and language, but not ethnicity or care status",
    4: "including ethnicity and care status, each such read held for a person's approval",
}
# Each tool's parameters, as the servers declare them (a test checks this against their schemas). A name not listed
# here never reaches a summary: the gateway holds a call before the tool checks its arguments, so it may be made up.
TOOL_PARAMS: dict[tuple[str, str], frozenset[str]] = {
    ("pupil-data", "search"): frozenset({"query", "urn", "limit"}),
    ("pupil-data", "get"): frozenset({"path", "limit"}),
    ("pupil-data", "aggregate"): frozenset({"table", "group_by", "measure", "where"}),
    ("pupil-data", "classification"): frozenset(),
    ("pupil-data", "roster"): frozenset({"urn", "year_group", "academic_year", "term"}),
    ("pupil-data", "pupil"): frozenset({"pupil_id", "urn"}),
    ("pupil-data", "draft"): frozenset({"urn", "pupil_ids", "kind"}),
    ("pupil-data", "write"): frozenset({"pupil_id", "urn", "column", "value", "reason"}),
    ("schools", "list"): frozenset(),
    ("schools", "classification"): frozenset(),
    ("directory", "roster"): frozenset({"urn", "year_group", "academic_year", "term"}),
    ("directory", "name"): frozenset({"pupil_id", "urn"}),
    ("special", "record"): frozenset({"pupil_id", "urn"}),
}
# Values a summary may show as they are (quote-request-values). Everything else an agent sent is left out of the
# sentence and shown on the approval page as quoted data: the summary must read as the gateway's words only.
LEFT_OUT = "see the values below"
# the data's own names (a test checks these against the manifest; the issuer's image doesn't carry the manifest)
DATA_TABLES = frozenset({"schools", "display_names", "personal_data_deprivation", "personal_data_school_census"})
DATA_COLUMNS = frozenset({
    "Psuedo ID", "Gender", "Ethnicity", "Language", "FSMeligible", "InCareAtCurrentSchool", "AcademicYear",
    "CensusTerm", "EnrolStatus", "AgeAtStartOfAcademicYear", "URN", "HomeArea", "SchoolArea", "DeprivationScore",
    "DeprivationDecile", "SchoolName", "SchoolLA", "DisplayName",
})  # fmt: skip
DATA_FILES = frozenset(f"synthetic/synthetic_{t}.csv" for t in DATA_TABLES) | {"synthetic/synthetic_manifest.json"}
FIXED_VALUES = {
    "year_group": {"10", "11"},
    "academic_year": {"2020/21", "2021/22", "2022/23", "2023/24"},
    "term": {"AUT", "SPR", "SUM"},
}
PUPIL_ID = re.compile(r"P\d{4}")
PLAIN_TOKEN = re.compile(r"[A-Za-z0-9_./-]{1,16}")
# tools whose data belongs to a school: without a urn constraint they reach all twelve
PER_SCHOOL_TOOLS = {"search", "aggregate", "roster", "pupil", "draft", "write", "name", "record"}


@lru_cache
def school_names() -> dict[str, str]:
    try:
        with SCHOOLS_PATH.open(newline="") as f:
            return {r["URN"]: r["SchoolName"] for r in csv.DictReader(f)}
    except OSError:
        return {}


def school(urn: str) -> str:
    name = school_names().get(urn)
    return f"{name} ({urn})" if name else urn


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _graded_level(clearance: int | None) -> int:
    from .graded import claimless_level  # noqa: PLC0415  (graded imports audit; keep this module light)

    return clearance if type(clearance) is int and 1 <= clearance <= 4 else claimless_level()  # noqa: PLR2004


def recognised(name: str, value) -> bool:
    """Whether a value an agent sent may appear in a summary as it is: one the gateway can name, or a short token."""
    if type(value) is int:
        return -10_000 < value < 10_000  # noqa: PLR2004
    if not isinstance(value, str):
        return False  # lists, objects, booleans: never inline
    if name == "urn":
        return value in school_names()
    if name in FIXED_VALUES:
        return value in FIXED_VALUES[name]
    if name == "column" or value in DATA_COLUMNS:
        return value in DATA_COLUMNS
    if name == "path":
        return value in DATA_FILES  # a path that isn't one of the data files is worth a look on the page
    return bool(PUPIL_ID.fullmatch(value) or value in DATA_TABLES or PLAIN_TOKEN.fullmatch(value))


def shown(name: str, value) -> str:
    """A value as a summary shows it: a school by name, a recognised value as it is, anything else left out."""
    if not recognised(name, value):
        return f"({name}: {LEFT_OUT})"
    return school(value) if name == "urn" else str(value)


def _others(count: int, what: str) -> str:
    return f"(and {count} other {what}{'' if count == 1 else 's'}: {LEFT_OUT})"


def tool_params(server: str, tools: list[str]) -> frozenset[str]:
    return frozenset().union(*(TOOL_PARAMS.get((server, t), frozenset()) for t in tools))


def entry_words(entry: dict, clearance: int | None = None) -> str:
    """One scope entry as a sentence fragment: what, where, for whom. `clearance` is the grant's effective one."""
    server = entry.get("server", "?")
    tools = entry.get("tools", [])
    what = _join([TOOL_WORDS.get((server, t), f"Use {server}.{t}") for t in tools]) or f"Use {server}"
    parts = [what]
    if server == GRADED_SERVER and set(tools) & GRADED_TOOLS:
        parts.append(GRADED_WORDS[_graded_level(clearance)])
    constraints = entry.get("constraints", {})
    if urns := constraints.get("urn"):
        parts.append("at " + _join([shown("urn", u) for u in urns]))
    elif set(tools) & PER_SCHOOL_TOOLS:
        # saying nothing would read as narrower than what is enforced
        parts.append("at every school")
    params = tool_params(server, tools)
    others = {k: v for k, v in constraints.items() if k != "urn"}
    for k, values in others.items():
        if k in params:
            parts.append(f"where {k} is " + _join([shown(k, v) for v in values]))
    if unknown := [k for k in others if k not in params]:
        parts.append(_others(len(unknown), "constraint"))
    pupils = (entry.get("audience") or {}).get("pupils")
    if isinstance(pupils, list):
        parts.append(f"for {len(pupils)} named pupil" + ("" if len(pupils) == 1 else "s"))
    if type(max_rows := entry.get("max_rows")) is int:
        parts.append(f"(at most {max_rows} rows a call)")
    if isinstance(rate := entry.get("rate"), dict):
        limits = []
        if "per_minute" in rate:
            limits.append(f"at most {rate['per_minute']} calls a minute")
        if "max_calls" in rate:
            limits.append(f"{rate['max_calls']} calls in all")
        if limits:
            parts.append("(" + ", ".join(limits) + ")")
    return " ".join(parts)


def until(exp: int | float | None) -> str:
    if not exp:
        return ""
    return "until " + time.strftime("%H:%M on %d %b", time.localtime(exp))


def lifetime(seconds: int) -> str:
    if seconds % 3600 == 0:
        h = seconds // 3600
        return f"for {h} hour" + ("" if h == 1 else "s")
    m = max(1, round(seconds / 60))
    return f"for {m} minute" + ("" if m == 1 else "s")


def grants_words(scope: list[dict], *, clearance: int | None = None, exp=None, ttl: int | None = None) -> str:
    sentences = [entry_words(e, clearance) for e in scope]
    text = ". ".join(sentences)
    if ttl:
        text += f", {lifetime(ttl)}"
    elif exp:
        text += f", {until(exp)}"
    if clearance is not None:
        text += f". Highest data level: {clearance}"
    return text + "."


def marks_level_4(scope: list[dict], clearance: int | None) -> bool:
    """Whether a grant reaches special category data (level 4): the special server, or clearance 4."""
    return any(e.get("server") in LEVEL_4_SERVERS for e in scope) or clearance == 4  # noqa: PLR2004


def action_words(server: str, tool: str, arguments: dict) -> str:
    """A held call in plain words. Values the gateway doesn't recognise, and argument names the tool doesn't take,
    are left out and pointed to: the approval page shows them all as quoted data (quote-request-values)."""
    params = TOOL_PARAMS.get((server, tool), frozenset())
    unknown = sorted(k for k in arguments if k not in params)
    extra = (" " + _others(len(unknown), "argument")) if unknown else ""
    arg = lambda k, default=None: shown(k, arguments.get(k, default))  # noqa: E731
    if (server, tool) == ("pupil-data", "write"):
        # the agent's `reason` was never part of the words; the page shows it with the other values
        return f"Change {arg('column')} to {arg('value')} for pupil {arg('pupil_id')} at {arg('urn')}{extra}"
    if tool == "draft":
        ids = arguments.get("pupil_ids")
        named = _join([shown("pupil_ids", p) for p in ids]) if isinstance(ids, list) else shown("pupil_ids", ids)
        return f"Draft {arg('kind', 'absence')} letters for {named} at {arg('urn')}{extra}"
    if tool == "record":
        return f"Read the ethnicity and care status of pupil {arg('pupil_id')} at {arg('urn')}{extra}"
    named = sorted((k, v) for k, v in arguments.items() if k in params)
    inline = ", ".join(f"{k}={v}" for k, v in named if recognised(k, v))
    left = "".join(f" ({k}: {LEFT_OUT})" for k, v in named if not recognised(k, v))
    what = TOOL_WORDS.get((server, tool), f"{server}.{tool}")
    return (f"{what} ({inline})" if inline else what) + left + extra


def agent_values(server: str, tools: list[str], values: dict) -> list[dict]:
    """Every name and value an agent sent, for the approval page to show verbatim: `known` is whether the tool
    takes that name."""
    params = tool_params(server, tools)
    return [{"name": k, "value": v, "known": k in params} for k, v in sorted(values.items())]
