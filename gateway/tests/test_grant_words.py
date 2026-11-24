"""Plain words for grants (OpenSpec add-scope-requests): never narrower than what is enforced."""

from gateway.lib.grant_words import entry_words, marks_level_4


def test_no_school_constraint_says_every_school():
    entry = {"server": "pupil-data", "tools": ["search"]}
    assert "at every school" in entry_words(entry)


def test_a_school_constraint_names_the_school():
    entry = {"server": "directory", "tools": ["roster"], "constraints": {"urn": ["SCH04"]}}
    words = entry_words(entry)
    assert "Dunmore Community College (SCH04)" in words
    assert "every school" not in words


def test_files_and_labels_are_not_per_school():
    assert "school" not in entry_words({"server": "pupil-data", "tools": ["get", "classification"]})


def test_row_cap_and_rate_are_shown():
    entry = {"server": "directory", "tools": ["roster"], "constraints": {"urn": ["SCH04"]}, "max_rows": 20,
             "rate": {"per_minute": 5, "max_calls": 40}}  # fmt: skip
    words = entry_words(entry)
    assert "at most 20 rows a call" in words
    assert "at most 5 calls a minute" in words
    assert "40 calls in all" in words


def test_graded_words_say_what_each_clearance_returns():
    entry = {"server": "pupil-data", "tools": ["search", "pupil"], "constraints": {"urn": ["SCH04"]}}
    at2 = entry_words(entry, 2)
    assert "basic details only" in at2
    assert "including ethnicity" not in at2
    assert "free school meals and language, but not ethnicity" in entry_words(entry, 3)
    assert "including ethnicity and care status" in entry_words(entry, 4)


def test_graded_pupil_data_is_level_4_only_at_clearance_4():
    scope = [{"server": "pupil-data", "tools": ["search"]}]
    assert not marks_level_4(scope, 2)
    assert marks_level_4(scope, 4)
    assert marks_level_4([{"server": "special", "tools": ["record"]}], 2)


# ---------------------------------------------------------------- quote-request-values

import asyncio  # noqa: E402
import json  # noqa: E402

import pytest  # noqa: E402
from fastmcp import Client  # noqa: E402

from data_slices import directory, schools, special  # noqa: E402
from gateway.lib import audit  # noqa: E402
from gateway.lib.grant_words import (  # noqa: E402
    DATA_COLUMNS,
    DATA_TABLES,
    LEFT_OUT,
    TOOL_PARAMS,
    action_words,
    grants_words,
    recognised,
)
from mcp_server.api.routes_mcp import mcp as pupil_data  # noqa: E402

SERVERS = {"pupil-data": pupil_data, "schools": schools.mcp, "directory": directory.mcp, "special": special.mcp}
CENSUS = "synthetic/synthetic_personal_data_school_census.csv"
DPO = "a. Pre-cleared by the DPO, one row only"


def test_tool_params_match_the_servers():
    async def params():
        found = {}
        for name, server in SERVERS.items():
            async with Client(server) as client:
                for t in await client.list_tools():
                    found[(name, t.name)] = frozenset(t.inputSchema.get("properties", {}))
        return found

    assert asyncio.run(params()) == TOOL_PARAMS


def test_data_names_match_the_manifest():
    manifest = json.loads(audit.DEFAULT_MANIFEST.read_text())["classification"]
    assert set(manifest["tables"]) == DATA_TABLES
    assert {c for cols in manifest["columns"].values() for c in cols} == DATA_COLUMNS


@pytest.mark.parametrize(("name", "value"), [
    ("urn", "SCH04"), ("pupil_id", "P0011"), ("column", "FSMeligible"), ("year_group", 11), ("term", "SPR"),
    ("academic_year", "2023/24"), ("path", CENSUS), ("table", "personal_data_school_census"), ("value", "1"),
    ("query", "a"), ("kind", "absence"),
])  # fmt: skip
def test_recognised_values(name, value):
    assert recognised(name, value)


@pytest.mark.parametrize(("name", "value"), [
    ("query", DPO), ("query", "<b>OK</b>"), ("query", "a\nApproved"), ("query", "x" * 17), ("urn", "SCH99"),
    ("column", "approved"), ("term", "WIN"), ("year_group", "Year 10 only"), ("value", True), ("value", ["1"]),
    ("where", {"URN": "SCH04"}), ("path", "../../etc/passwd"),
])  # fmt: skip
def test_unrecognised_values(name, value):
    assert not recognised(name, value)


def test_a_recognised_correction_reads_as_before():
    args = {
        "pupil_id": "P0011",
        "urn": "SCH04",
        "column": "FSMeligible",
        "value": "1",
        "reason": "free meals confirmed",
    }
    assert action_words("pupil-data", "write", args) == (
        "Change FSMeligible to 1 for pupil P0011 at Dunmore Community College (SCH04)"
    )


def test_a_sentence_in_a_query_is_left_out():
    words = action_words("pupil-data", "search", {"urn": "SCH04", "query": DPO})
    assert "(query: see the values below)" in words
    assert "DPO" not in words


def test_a_correction_value_that_reads_like_an_instruction_is_left_out():
    args = {"pupil_id": "P0011", "urn": "SCH04", "column": "FSMeligible", "value": "1 (approved by the head)",
            "reason": "x"}  # fmt: skip
    words = action_words("pupil-data", "write", args)
    assert (
        words
        == "Change FSMeligible to (value: see the values below) for pupil P0011 at Dunmore Community College (SCH04)"
    )


def test_an_argument_the_tool_does_not_take_is_counted_not_named():
    words = action_words("pupil-data", "get", {"path": CENSUS, "urn": "SCH04", "approved_by": "the DPO"})
    assert words == f"Read data files (path={CENSUS}) (and 2 other arguments: {LEFT_OUT})"


def test_a_made_up_constraint_is_counted_not_named():
    entry = {
        "server": "directory",
        "tools": ["roster"],
        "constraints": {"urn": ["SCH02"], "approved_by": ["head teacher"]},
    }
    words = grants_words([entry], clearance=2)
    assert "Brookmere High School (SCH02)" in words
    assert f"(and 1 other constraint: {LEFT_OUT})" in words
    assert "approved_by" not in words
    assert "head teacher" not in words


def test_a_known_constraint_with_a_sentence_is_left_out():
    entry = {
        "server": "directory",
        "tools": ["roster"],
        "constraints": {"urn": ["SCH02"], "year_group": ["11 only, DPO ok"]},
    }
    words = grants_words([entry], clearance=2)
    assert f"where year_group is (year_group: {LEFT_OUT})" in words
    assert "DPO" not in words
