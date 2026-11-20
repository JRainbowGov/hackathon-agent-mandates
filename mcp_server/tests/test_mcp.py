import asyncio

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from mcp_server.api import routes_mcp
from mcp_server.api.routes_mcp import mcp


def call(tool, **args):
    async def run():
        async with Client(mcp) as client:
            return await client.call_tool(tool, args)

    return asyncio.run(run())


def test_tools_listed():
    async def run():
        async with Client(mcp) as client:
            return await client.list_tools()

    assert sorted(t.name for t in asyncio.run(run())) == [
        "aggregate",
        "classification",
        "draft",
        "get",
        "pupil",
        "roster",
        "search",
        "write",
    ]


def test_search_all_and_by_school():
    assert {r["URN"] for r in call("search", query="spr", urn="SCH01").data} == {"SCH01"}
    # no auth: every school's pupils are reachable - middleware is expected to block this
    assert len({r["URN"] for r in call("search", query="SPR", limit=10000).data}) == 12
    assert call("search", query="SCH02", urn="SCH01").data == []
    assert call("search", query="SPR", urn="").data == []  # an empty urn is not "every school"
    assert len(call("search", query="SPR", limit=5).data) == 5


def test_get_and_traversal_blocked():
    assert call("get", path="synthetic/synthetic_manifest.json").data["data_source"] == "synthetic"
    with pytest.raises(ToolError):
        call("get", path="../pyproject.toml")


def test_get_csv_returns_rows_up_to_limit():
    schools = call("get", path="synthetic/synthetic_schools.csv").data
    assert len(schools) == 12
    assert schools[0] == {"URN": "SCH01", "SchoolName": "Ashfield Academy", "SchoolLA": "SYN"}
    census = call("get", path="synthetic/synthetic_personal_data_school_census.csv", limit=5).data
    assert len(census) == 5
    assert census[0]["Psuedo ID"] == "P0001"
    assert call("get", path="synthetic/synthetic_manifest.json").data["classification"]["tables"]["schools"] == 1


def test_aggregate_counts_flag_per_group():
    spring = {"CensusTerm": "SPR", "AcademicYear": "2023/24"}
    rows = call("aggregate", table="personal_data_school_census", group_by=["URN"], measure="FSMeligible", where=spring)
    assert len(rows.data) == 12
    assert all(set(r) == {"URN", "total", "count"} and r["count"] <= r["total"] for r in rows.data)
    with pytest.raises(ToolError):
        call("aggregate", table="../synthetic/schools", group_by=["URN"], measure="FSMeligible")
    with pytest.raises(ToolError):
        call("aggregate", table="schools", group_by=["URN"], measure="NoSuchColumn")


def test_classification_labels_every_column():
    labels = call("classification").data
    assert labels["tables"]["personal_data_school_census"] == 4
    assert labels["columns"]["personal_data_school_census"]["InCareAtCurrentSchool"] == 4
    assert labels["columns"]["schools"] == {"URN": 1, "SchoolName": 1, "SchoolLA": 1}


def test_roster_keeps_to_school_and_year():
    rows = call("roster", urn="SCH04", year_group=11).data
    assert rows
    assert all(set(r) == {"Psuedo ID", "DisplayName"} for r in rows)
    ids = {r["Psuedo ID"] for r in rows}
    census = call("search", query="2023/24", urn="SCH04", limit=10000).data
    assert ids == {r["Psuedo ID"] for r in census if r["CensusTerm"] == "SPR" and r["AgeAtStartOfAcademicYear"] == "15"}
    with pytest.raises(ToolError):
        call("roster", urn="SCH04", year_group=7)


def test_pupil_full_record_only_at_its_school():
    pid = call("roster", urn="SCH04", year_group=11).data[0]["Psuedo ID"]
    record = call("pupil", pupil_id=pid, urn="SCH04").data
    assert {"Ethnicity", "InCareAtCurrentSchool", "DisplayName", "DeprivationDecile"} <= set(record)
    assert call("pupil", pupil_id=pid, urn="SCH05").data == {}


def test_draft_skips_other_schools():
    pid = call("roster", urn="SCH04", year_group=11).data[0]["Psuedo ID"]
    other = call("roster", urn="SCH05", year_group=11).data[0]["Psuedo ID"]
    letters = call("draft", urn="SCH04", pupil_ids=[pid, other]).data
    assert [letter["Psuedo ID"] for letter in letters] == [pid]


def test_write_appends_correction(tmp_path, monkeypatch):
    monkeypatch.setattr(routes_mcp, "WRITES_PATH", tmp_path / "corrections.jsonl")
    pid = call("roster", urn="SCH04", year_group=11).data[0]["Psuedo ID"]
    entry = call("write", pupil_id=pid, urn="SCH04", column="FSMeligible", value="1", reason="test").data
    assert entry["after"] == "1"
    assert (tmp_path / "corrections.jsonl").read_text().count("\n") == 1
    with pytest.raises(ToolError):
        call("write", pupil_id=pid, urn="SCH04", column="URN", value="SCH05", reason="move")
    with pytest.raises(ToolError):
        call("write", pupil_id=pid, urn="SCH05", column="FSMeligible", value="1", reason="wrong school")
