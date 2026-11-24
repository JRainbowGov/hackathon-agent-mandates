"""Safe counts (OpenSpec add-safe-counts): counts can't name a child, through grouping, filtering or small groups."""

import asyncio
import json

import pytest

from gateway import cli
from gateway.lib import audit, safe_counts
from gateway.lib.common import priv_from_pem
from gateway.tests.test_gateway import gw  # noqa: F401  (fixture)

CENSUS = "personal_data_school_census"
LEAK_FILTER = {"table": CENSUS, "group_by": ["Ethnicity", "URN"], "measure": "FSMeligible",
               "where": {"Psuedo ID": "P0011"}}  # fmt: skip
LEAK_GROUP = {"table": CENSUS, "group_by": ["Psuedo ID", "Ethnicity", "URN"], "measure": "FSMeligible"}


def counts_caller(state, *, claims=None, constraints=None, name="counts.jwt"):
    scope = [{"server": "pupil-data", "tools": ["aggregate"], "constraints": constraints or {"table": [CENSUS]}}]
    args = ["--state", str(state), "issue", "--agent-key", str(state / "agent.pem"), "-o", str(state / name),
            "--scope", json.dumps(scope)]  # fmt: skip
    if claims:
        args += ["--claims", json.dumps(claims)]
    cli.main(args)
    mandate = (state / name).read_text()
    priv = priv_from_pem((state / "agent.pem").read_bytes())

    def call(client, **arguments):
        body = cli.sign_request(priv, server="pupil-data", tool="aggregate", arguments=arguments, mandate=mandate)
        return client.post("/tools/call", json=body)

    return call


def events():
    return asyncio.run(audit.get_store().all_events())


# ---------------------------------------------------------------- column rules (unit)


@pytest.mark.parametrize(
    ("arguments", "claims", "expected"),
    [
        (LEAK_FILTER, {"clearance": 4}, ("COUNT_COLUMN_REFUSED", "Psuedo ID")),
        (LEAK_GROUP, {"clearance": 4}, ("COUNT_COLUMN_REFUSED", "Psuedo ID")),
        ({"group_by": ["URN", "Ethnicity"], "measure": "FSMeligible"}, {}, ("COUNT_COLUMN_REFUSED", "Ethnicity")),
        (
            {"group_by": ["URN"], "measure": "InCareAtCurrentSchool"},
            {"clearance": True},
            ("COUNT_COLUMN_REFUSED", "InCareAtCurrentSchool"),
        ),
        ({"group_by": ["URN", "Ethnicity"], "measure": "FSMeligible"}, {"clearance": 4}, None),
        (
            {"group_by": ["URN", "Gender", "Ethnicity"], "measure": "FSMeligible"},
            {"clearance": 4},
            ("COUNT_TOO_FINE", "at most 2 group_by columns"),
        ),
        (
            {"group_by": ["URN"], "measure": "FSMeligible", "where": {"Language": "1_ENG"}},
            {},
            ("COUNT_TOO_FINE", "where on Language"),
        ),
        ({"group_by": ["URN"], "measure": "FSMeligible", "where": {"CensusTerm": "SPR"}}, {}, None),
        (
            {"group_by": "URN", "measure": "FSMeligible"},
            {},
            ("COUNT_COLUMN_REFUSED", "group_by must be a list of column names, measure a column name"),
        ),
    ],
)
def test_column_rules(arguments, claims, expected):
    assert safe_counts.check(arguments, claims) == expected


def test_k_can_be_raised_not_lowered():
    assert safe_counts.k_for({"counts": {"k": 3}}) == 10
    assert safe_counts.k_for({"counts": {"k": 20}}) == 20
    assert safe_counts.k_for({"counts": {"k": True}}) == 10
    assert safe_counts.k_for(None) == 10


def test_rounding():
    assert [safe_counts.round5(n) for n in (0, 1, 2, 3, 7, 8, 112, 113)] == [0, 0, 0, 5, 5, 10, 110, 115]


def test_release_suppresses_small_groups_and_cells():
    rows = [{"URN": "A", "Psuedo ID": f"P{i:04d}", "total": 3, "count": int(i == 0)} for i in range(12)]  # 1 flagged
    rows += [{"URN": "B", "Psuedo ID": f"P{i:04d}", "total": 1, "count": 0} for i in range(100, 105)]  # 5 pupils
    rows += [{"URN": "C", "Psuedo ID": f"P{i:04d}", "total": 2, "count": int(i < 210)} for i in range(200, 211)]
    out = safe_counts.release(rows, ["URN"], 10, per_pupil=True)
    assert out == [
        {"URN": "A", "total": 10, "count": None},  # 12 pupils, 1 flagged: the count is hidden
        {"URN": "C", "total": 10, "count": None},  # 11 pupils, 10 flagged: the 1 without is hidden
        {"suppressed_groups": 1},  # B (5 pupils) dropped, with no key
    ]
    assert safe_counts.release(rows, ["URN"], 20, per_pupil=True) == [{"suppressed_groups": 3}]


# ---------------------------------------------------------------- through the gateway


def test_eval_counts_case_is_released_in_pupils(gw):  # noqa: F811
    client, _, state = gw
    call = counts_caller(state, constraints={"table": [CENSUS], "measure": ["FSMeligible"]})
    r = call(client, table=CENSUS, group_by=["URN"], measure="FSMeligible")
    assert r.status_code == 200, r.text
    rows = r.json()["result"]
    assert len(rows) == 12
    assert all(row["total"] % 5 == 0 and row["count"] is not None and row["count"] % 5 == 0 for row in rows)
    assert not any("suppressed_groups" in row for row in rows)
    assert {row["URN"] for row in rows} == {f"SCH{i:02d}" for i in range(1, 13)}
    (event,) = events()
    assert event["max_pii_level"] == 3
    assert event["pupil_ids_returned"] == []


def test_both_leaks_are_refused_before_forwarding(gw, monkeypatch):  # noqa: F811
    client, _, state = gw
    call = counts_caller(state)

    async def never(*_args, **_kwargs):
        msg = "forwarded"
        raise AssertionError(msg)

    monkeypatch.setattr("gateway.main._forward", never)
    for leak in (LEAK_FILTER, LEAK_GROUP):
        r = call(client, **leak)
        assert (r.status_code, r.json()["decision"]["reason_code"]) == (403, "COUNT_COLUMN_REFUSED")
        assert "result" not in r.json()
    assert [e["reason_code"] for e in events()] == ["COUNT_COLUMN_REFUSED", "COUNT_COLUMN_REFUSED"]


def test_one_in_care_pupil_is_not_counted(gw):  # noqa: F811
    client, _, state = gw
    call = counts_caller(state, claims={"clearance": 4})
    r = call(client, table=CENSUS, group_by=["URN"], measure="InCareAtCurrentSchool")
    assert r.status_code == 200, r.text
    by_school = {row["URN"]: row for row in r.json()["result"]}
    assert by_school["SCH07"] == {"URN": "SCH07", "total": 110, "count": None}  # 112 pupils, exactly 1 in care
    assert by_school["SCH02"]["count"] is None  # none in care: hidden too, or 0 against null would name the child


def test_differencing_gives_multiples_of_five(gw):  # noqa: F811
    client, _, state = gw
    call = counts_caller(state, claims={"clearance": 4})
    whole = call(client, table=CENSUS, group_by=["URN"], measure="FSMeligible").json()["result"]
    spring = call(client, table=CENSUS, group_by=["URN"], measure="FSMeligible",
                  where={"CensusTerm": "SPR"}).json()["result"]  # fmt: skip
    for row in whole + spring:
        assert row["total"] % 5 == 0
        assert row["count"] is None or row["count"] % 5 == 0


def test_tables_without_pupils_are_rounded_rows(gw):  # noqa: F811
    client, _, state = gw
    call = counts_caller(state, constraints={"table": ["schools"]})
    r = call(client, table="schools", group_by=["SchoolLA"], measure="URN")
    assert r.status_code == 200, r.text
    assert r.json()["result"] == [{"SchoolLA": "SYN", "total": 10, "count": 0}]  # 12 schools, rounded


def test_zero_and_everyone_are_hidden_like_small_counts():
    none = [{"URN": "A", "Psuedo ID": f"P{i:04d}", "total": 1, "count": 0} for i in range(20)]
    every = [{"URN": "B", "Psuedo ID": f"P{i:04d}", "total": 1, "count": 1} for i in range(100, 120)]
    out = safe_counts.release(none + every, ["URN"], 10, per_pupil=True)
    assert out == [{"URN": "A", "total": 20, "count": None}, {"URN": "B", "total": 20, "count": None}]


def test_filtered_counts_cant_tell_who_is_in_care(gw):  # noqa: F811
    """The live attack: SCH07's one pupil in care, narrowed by overlapping filters. Every answer must look the same."""
    client, _, state = gw
    call = counts_caller(state, claims={"clearance": 4})
    answers = set()
    for where in ({"Gender": "F"}, {"Gender": "M"}, {"AcademicYear": "2020/21"}, {"AcademicYear": "2021/22"},
                  {"AcademicYear": "2022/23"}, {"AcademicYear": "2023/24"}, {"EnrolStatus": "C"}):  # fmt: skip
        r = call(
            client, table=CENSUS, group_by=["URN"], measure="InCareAtCurrentSchool", where={"URN": "SCH07", **where}
        )
        assert r.status_code == 200, r.text
        answers.update(row.get("count") for row in r.json()["result"] if row.get("URN") == "SCH07")
    assert answers <= {None}


def test_claimless_counts_cant_group_by_level_3(gw):  # noqa: F811
    client, _, state = gw
    call = counts_caller(state)
    r = call(client, table=CENSUS, group_by=["Language"], measure="FSMeligible", where={"URN": "SCH04"})
    assert (r.status_code, r.json()["decision"]["reason_code"]) == (403, "COUNT_COLUMN_REFUSED")
    # the measure may still be level 3: the organisers' school-level free school meal numbers
    assert call(client, table=CENSUS, group_by=["URN"], measure="FSMeligible").status_code == 200
    at3 = counts_caller(state, claims={"clearance": 3})
    assert at3(client, table=CENSUS, group_by=["Language"], measure="FSMeligible").status_code == 200
