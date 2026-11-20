"""The synthetic extract has the workbook schema, is reproducible and hits its base rates."""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from pydantic import TypeAdapter

from mcp_server.synth.generate import classification, generate_extract
from mcp_server.synth.pupils import generate_pupils
from mcp_server.synth.schemas import DISPLAY_NAMES, PSEUDO_ID, SYNTHETIC_SCHOOL_NAMES, TABLE_COLUMNS, TABLES

SMALL_N = 400


@pytest.fixture(scope="session")
def synth_cfg() -> dict:
    cfg = yaml.safe_load((Path(__file__).parents[1] / "synth.yaml").read_text())
    cfg["n_per_cohort"] = SMALL_N
    cfg["seed"] = 7
    return cfg


@pytest.fixture(scope="session")
def extract(synth_cfg: dict) -> dict[str, pd.DataFrame]:
    tables, _ = generate_extract(synth_cfg)
    return tables


def test_manifest_classifies_every_table_with_a_known_level(synth_cfg):
    _, manifest = generate_extract(synth_cfg)
    levels, tables = manifest["classification"]["levels"], manifest["classification"]["tables"]
    assert set(tables) == set(TABLES)
    assert set(tables.values()) <= set(levels)
    assert levels[tables["schools"]] == "Public Information"


def test_unlabelled_table_is_rejected(synth_cfg):
    cfg = copy.deepcopy(synth_cfg)
    del cfg["classification"]["tables"]["schools"]
    with pytest.raises(ValueError, match="missing \\['schools'\\]"):
        classification(cfg)


def test_manifest_classifies_every_column(synth_cfg):
    _, manifest = generate_extract(synth_cfg)
    columns = manifest["classification"]["columns"]
    assert {t: list(c) for t, c in columns.items()} == TABLE_COLUMNS
    assert columns["personal_data_school_census"]["Ethnicity"] == 4
    assert columns["personal_data_school_census"]["URN"] == 1
    assert columns["display_names"]["DisplayName"] == 2  # unlisted: takes the table's level


@pytest.mark.parametrize("column, level", [("NoSuchColumn", 1), ("URN", 9), ("DisplayName", 3)])
def test_bad_column_level_is_rejected(synth_cfg, column, level):
    cfg = copy.deepcopy(synth_cfg)
    cfg["classification"]["columns"] = {"display_names": {column: level}}
    with pytest.raises(ValueError, match="classification.columns"):
        classification(cfg)


def test_every_table_has_workbook_columns_in_order(extract):
    for key, cols in TABLE_COLUMNS.items():
        assert list(extract[key].columns) == cols, key


def test_every_row_validates_against_its_model(extract):
    for key, model in TABLES.items():
        TypeAdapter(list[model]).validate_python(extract[key].to_dict("records"))


def test_same_seed_is_byte_identical(synth_cfg):
    a, _ = generate_extract(copy.deepcopy(synth_cfg))
    b, _ = generate_extract(copy.deepcopy(synth_cfg))
    for key in a:
        pd.testing.assert_frame_equal(a[key], b[key])


def test_pseudo_ids_are_short_pupil_numbers(extract):
    for key, cols in TABLE_COLUMNS.items():
        if PSEUDO_ID in cols:
            assert extract[key][PSEUDO_ID].str.fullmatch(r"P\d{4}").all(), key


def test_every_pupil_has_one_display_name_matching_census_gender(extract):
    names = extract["display_names"]
    census = extract["personal_data_school_census"].drop_duplicates(PSEUDO_ID).set_index(PSEUDO_ID)
    assert list(names.columns) == DISPLAY_NAMES
    assert set(names[PSEUDO_ID]) == set(census.index)
    assert not names[PSEUDO_ID].duplicated().any()
    assert names["DisplayName"].str.contains(" ").all()
    assert (names.set_index(PSEUDO_ID)["Gender"] == census["Gender"]).all()


def test_schools_have_invented_names_and_every_census_urn_exists(extract):
    schools = extract["schools"]
    assert set(schools["SchoolName"]) <= set(SYNTHETIC_SCHOOL_NAMES)
    assert schools["URN"].str.fullmatch(r"SCH\d{2}").all()
    assert extract["personal_data_school_census"]["URN"].isin(set(schools["URN"])).all()


def test_indicator_rates_hit_base_rates(synth_cfg):
    # n=4000 keeps binomial noise under 0.7 points, so 2 points is a 3-sigma check on the calibration
    pupils = generate_pupils(np.random.default_rng(7), 4000, synth_cfg)
    rates = synth_cfg["base_rates"]
    for col, key in (("fsm", "fsm"), ("ehcp", "ehcp"), ("sen_k", "sen_support"), ("eal", "eal")):
        assert abs(pupils[col].mean() - rates[key]) < 0.02, col


def test_deprivation_decile_ranks_the_score(extract):
    dep = extract["personal_data_deprivation"]
    assert dep.loc[dep["DeprivationScore"].idxmax(), "DeprivationDecile"] == 10
    assert dep.loc[dep["DeprivationScore"].idxmin(), "DeprivationDecile"] == 1
