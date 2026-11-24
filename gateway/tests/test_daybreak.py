# ruff: noqa: F811, SLF001  (the shared flow fixture; the nonce store is checked directly)
"""Regressions for the Daybreak security review of main (24 Nov): each test is one finding's attack."""

import json
import secrets
import time

import jwt
import pytest

from gateway.lib import graded
from gateway.lib.common import generate_keypair, priv_from_pem, sign_bytes
from gateway.lib.gateway_verify import Request
from gateway.lib.grant_issue import grant_fields
from gateway.lib.scope_math import Invalid, validate_entry
from gateway.tests.test_scope_requests import events, flow, jti_of, roster  # noqa: F401  (fixture)

NAMES_FILE = "synthetic/synthetic_display_names.csv"
NAMES_SCH04 = [{"server": "directory", "tools": ["name"], "constraints": {"urn": ["SCH04"]}}]


def _claims(token: str) -> dict:
    return jwt.decode(token, options={"verify_signature": False})


def _every_school(f) -> None:
    path = f["state"] / "principals.json"
    ceiling = json.loads(path.read_text())
    for person in ceiling.values():
        person["urns"] = "*"
    path.write_text(json.dumps(ceiling))


def _supervised(f, supervisor, scope, approved=None):
    """A helper asks for `scope`; `supervisor` decides. (status, body, helper key, request id)."""
    helper_key, _ = generate_keypair()
    helper = f["mandate"](roster("SCH01"), key=helper_key, clearance=2)
    status, resp = f["request"](helper, key=helper_key, scope=scope)
    assert status == 200, resp
    rid = resp["result"]["request_id"]
    extra = {"approved": approved} if approved else {}
    status, resp = f["call"](f["client"], supervisor, "grants", "decide", request_id=rid, decision="approve", **extra)
    return status, resp, helper_key, rid


# ---------------------------------------------------------------- 1: a held release reaches no further


def test_released_held_get_reads_only_that_file(flow):
    f = flow
    _every_school(f)  # otherwise the request stops at the ceiling and the test proves nothing
    census = [{"server": "pupil-data", "tools": ["get"], "constraints": {"path": [graded.CENSUS_FILE]}}]
    token = f["mandate"](census, deny=[], clearance=4)
    status, resp = f["call"](f["client"], token, "pupil-data", "get", path=graded.CENSUS_FILE)
    assert status == 202
    held = {"decision_id": resp["decision"]["decision_id"], "server": "pupil-data", "tool": "get",
            "arguments": {"path": graded.CENSUS_FILE}}  # fmt: skip
    status, resp = f["request"](token, held=held)
    assert status == 200, resp
    v = resp["result"]
    f["decide"](v["request_id"], v["number"], session=f["login"]())
    child = f["call"](f["client"], token, "grants", "status", request_id=v["request_id"])[1]["result"]["mandate"]
    assert _claims(child)["scope"][0]["constraints"] == {"path": [graded.CENSUS_FILE]}

    status, resp = f["call"](f["client"], child, "pupil-data", "get", path=NAMES_FILE)
    assert status == 403
    assert "result" not in resp
    status, resp = f["call"](f["client"], child, "pupil-data", "get", path=graded.CENSUS_FILE)
    assert (status, resp["decision"]["reason_code"]) == (200, "PREAPPROVED")


def test_a_held_release_mandate_allows_only_its_released_calls(flow):
    """Even a call its scope would allow, if it isn't one of the released ones."""
    f = flow
    _every_school(f)
    scope = [{"server": "pupil-data", "tools": ["pupil"], "constraints": {"urn": ["SCH04"]}}]
    token = f["mandate"](scope, deny=[], clearance=4)
    args = {"urn": "SCH04", "pupil_id": "P0011"}
    status, resp = f["call"](f["client"], token, "pupil-data", "pupil", **args)
    assert status == 202
    held = {"decision_id": resp["decision"]["decision_id"], "server": "pupil-data", "tool": "pupil", "arguments": args}
    v = f["request"](token, held=held)[1]["result"]
    f["decide"](v["request_id"], v["number"], session=f["login"]())
    child = f["call"](f["client"], token, "grants", "status", request_id=v["request_id"])[1]["result"]["mandate"]
    status, resp = f["call"](f["client"], child, "grants", "self")
    assert status == 200  # its own grants are still readable
    status, resp = f["call"](f["client"], child, "pupil-data", "pupil", **args)
    assert (status, resp["decision"]["reason_code"]) == (200, "PREAPPROVED")


# ---------------------------------------------------------------- 2: a supervisor's deny rules travel


def test_supervisor_cannot_pass_on_a_tool_it_is_denied(flow):
    f = flow
    supervisor = f["mandate"](NAMES_SCH04, deny=["directory.name"], clearance=2, can_delegate=True)
    status, resp, _, _ = _supervised(f, supervisor, NAMES_SCH04)
    assert (status, resp["decision"]["reason_code"]) == (403, "EXCEEDS_SUPERVISOR")


# ---------------------------------------------------------------- 3: rates are checked, never widened


def test_an_approval_cannot_raise_the_requested_rate(flow):
    f = flow
    asked = [{**roster("SCH04")[0], "rate": {"max_calls": 1}}]
    supervisor = f["mandate"](roster("SCH04"), clearance=2, can_delegate=True)
    wider = {"scope": [{**asked[0], "rate": {"max_calls": 999999}}]}
    status, resp, _, _ = _supervised(f, supervisor, asked, approved=wider)
    assert (status, resp["decision"]["reason_code"]) == (403, "NOT_NARROWER")
    dropped = {"scope": roster("SCH04")}  # no rate at all is no limit at all
    status, resp, _, _ = _supervised(f, supervisor, asked, approved=dropped)
    assert (status, resp["decision"]["reason_code"]) == (403, "NOT_NARROWER")


def test_supervisor_cannot_approve_a_looser_rate_than_its_own(flow):
    f = flow
    supervisor = f["mandate"]([{**roster("SCH04")[0], "rate": {"max_calls": 1}}], clearance=2, can_delegate=True)
    status, resp, _, _ = _supervised(f, supervisor, [{**roster("SCH04")[0], "rate": {"max_calls": 5}}])
    assert (status, resp["decision"]["reason_code"]) == (403, "EXCEEDS_SUPERVISOR")
    status, resp, _, _ = _supervised(f, supervisor, [{**roster("SCH04")[0], "rate": {"max_calls": 1}}])
    assert status == 200


@pytest.mark.parametrize(
    "rate", [{}, {"max_calls": 0}, {"max_calls": True}, {"max_calls": "5"}, {"per_hour": 5}, [5], {"per_minute": -1}]
)
def test_a_malformed_rate_is_refused(rate):
    with pytest.raises(Invalid):
        validate_entry({**roster("SCH04")[0], "rate": rate})


# ---------------------------------------------------------------- 4: row caps


@pytest.mark.parametrize("max_rows", [-1, 101, True, "5", 2.5])
def test_a_malformed_row_cap_is_refused(max_rows):
    with pytest.raises(Invalid):
        validate_entry({**roster("SCH04")[0], "max_rows": max_rows})


@pytest.mark.parametrize("max_rows", [-1, "5", None])
def test_a_malformed_row_cap_on_a_mandate_grants_no_rows(max_rows):
    # the MCP server cuts results to the grant's max_rows; an unreadable cap must not become the default 100
    entry = {**roster("SCH04")[0], "max_rows": max_rows}
    assert grant_fields({"clearance": 2}, entry, "directory", "roster")["max_rows"] == 0


# ---------------------------------------------------------------- 5: nonces


def _raw_call(f, token, nonce, ts=None):
    priv = priv_from_pem((f["state"] / "agent.pem").read_bytes())
    req = Request(server="schools", tool="list", arguments={}, mandate=token, nonce=nonce,
                  ts=ts or int(time.time()), sig="")  # fmt: skip
    req.sig = sign_bytes(priv, req.signing_input())
    return f["client"].post("/tools/call", json=req.__dict__)


def test_an_oversized_nonce_is_refused_and_recorded(flow):
    f = flow
    token = f["mandate"]([{"server": "schools", "tools": ["list"]}], clearance=2)
    r = _raw_call(f, token, "x" * 100_000)
    assert (r.status_code, r.json()["decision"]["reason_code"]) == (403, "POP_FAILED")
    assert any(e["decision_id"] == r.json()["decision"]["decision_id"] for e in events(jti_of(token)))


def test_old_nonces_are_forgotten_but_never_replayable(flow, monkeypatch):
    f = flow
    from gateway import main  # noqa: PLC0415

    token = f["mandate"]([{"server": "schools", "tools": ["list"]}], clearance=2)
    nonce = secrets.token_urlsafe(16)
    assert _raw_call(f, token, nonce).status_code == 200
    assert _raw_call(f, token, nonce).json()["decision"]["reason_code"] == "POP_FAILED"
    gateway = main.state["gateway"]
    later = time.time() + 1000
    monkeypatch.setattr(time, "time", lambda: later)
    gateway._forget_old_nonces(force=True)
    assert nonce not in gateway._seen_nonces  # its timestamp is out of the window now, so it can't come back


# ---------------------------------------------------------------- 6: a malformed request is refused, not a 500


@pytest.mark.parametrize(
    "scope",
    [
        [{"server": [], "tools": ["name"]}],
        [{"server": "directory", "tools": [["name"]]}],
        [{"server": "directory", "tools": ["name"], "constraints": {"urn": [["SCH04"]]}}],
        [{"server": "directory", "tools": ["name"], "constraints": {"urn": [{"a": 1}]}}],
    ],
)
def test_a_malformed_grant_request_is_an_audited_refusal(flow, scope):
    f = flow
    token = f["mandate"](roster("SCH04"), clearance=2)
    status, resp = f["request"](token, scope=scope)
    assert (status, resp["decision"]["reason_code"]) == (403, "REQUEST_INVALID")
    assert any(e["decision_id"] == resp["decision"]["decision_id"] for e in events(jti_of(token)))


# ---------------------------------------------------------------- 7: the budget is the allowing entry's


def test_the_rate_counted_is_the_entry_that_allowed_the_call(flow):
    f = flow
    scope = [
        {**NAMES_SCH04[0], "audience": {"pupils": ["P0099"]}},
        {**NAMES_SCH04[0], "audience": {"pupils": ["P0011"]}, "rate": {"max_calls": 1}},
    ]  # fmt: skip
    token = f["mandate"](scope, clearance=2)
    first = f["call"](f["client"], token, "directory", "name", urn="SCH04", pupil_id="P0011")
    assert first[0] == 200, first
    second = f["call"](f["client"], token, "directory", "name", urn="SCH04", pupil_id="P0011")
    assert second[0] == 429, second


# ---------------------------------------------------------------- a held release is never reused as standing access


def test_held_releases_are_not_offered_for_reuse(flow):
    import issuer.app as issuer  # noqa: PLC0415

    f = flow
    scope = [{"server": "pupil-data", "tools": ["pupil"], "constraints": {"urn": ["SCH04"]}}]
    token = f["mandate"](scope, deny=[], clearance=4)
    args = {"urn": "SCH04", "pupil_id": "P0011"}
    _, resp = f["call"](f["client"], token, "pupil-data", "pupil", **args)
    held = {"decision_id": resp["decision"]["decision_id"], "server": "pupil-data", "tool": "pupil", "arguments": args}
    v = f["request"](token, held=held)[1]["result"]
    f["decide"](v["request_id"], v["number"], session=f["login"]())
    assert issuer.store().get(v["request_id"])["status"] == "approved"
    assert issuer.store().approved_for(jti_of(token)) == []
