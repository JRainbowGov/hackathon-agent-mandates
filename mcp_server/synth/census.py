"""Census and deprivation rows for a cohort."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from mcp_server.synth.schemas import PERSONAL_DATA_DEPRIVATION, PERSONAL_DATA_SCHOOL_CENSUS, PSEUDO_ID, TERMS

if TYPE_CHECKING:
    from mcp_server.synth.academic_year import AcademicYear

TERM_CODES = {"Autumn": "AUT", "Spring": "SPR", "Summer": "SUM"}
AGE_OFFSET = 4  # a Year N pupil is N + 4 at 31 August before the year starts
EAL_CODE = "2_OTH"
ENGLISH_CODE = "1_ENG"


def _as_int(values: pd.Series | np.ndarray) -> np.ndarray:
    return np.asarray(values, dtype=bool).astype(int)


def census_block(
    pupils: pd.DataFrame,
    ids: np.ndarray,
    year: AcademicYear,
    term: str,
    nc_year: int,
    *,
    enrol: np.ndarray,
    urns: np.ndarray,
) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            PSEUDO_ID: ids,
            "Gender": pupils["Gender"].to_numpy(),
            "Ethnicity": pupils["EthnicGroupMajor"].to_numpy(),
            "Language": np.where(pupils["eal"], EAL_CODE, ENGLISH_CODE),
            "FSMeligible": _as_int(pupils["fsm"]),
            "InCareAtCurrentSchool": _as_int(pupils["in_care"]),
            "AcademicYear": year.label,
            "CensusTerm": TERM_CODES[term],
            "EnrolStatus": enrol,
            "AgeAtStartOfAcademicYear": nc_year + AGE_OFFSET,
            "URN": urns,
        }
    )
    return frame[PERSONAL_DATA_SCHOOL_CENSUS]


def census_rows(
    rng: np.random.Generator,
    pupils: pd.DataFrame,
    ids: np.ndarray,
    year: AcademicYear,
    nc_year: int,
    *,
    cfg: dict,
    urns: np.ndarray,
) -> pd.DataFrame:
    """Census rows for the previous year (3 terms) and the scoring year (autumn, spring)."""
    n = len(pupils)
    current = np.full(n, "C", dtype=object)
    blocks = [census_block(pupils, ids, year.previous, term, nc_year - 1, enrol=current, urns=urns) for term in TERMS]
    blocks.append(census_block(pupils, ids, year, "Autumn", nc_year, enrol=current, urns=urns))
    spring_enrol = np.where(rng.random(n) < float(cfg["census"]["subsidiary_share"]), "S", "C")
    keep = rng.random(n) >= float(cfg["census"]["missing_spring_share"])
    spring = census_block(pupils, ids, year, "Spring", nc_year, enrol=spring_enrol, urns=urns)
    blocks.append(spring[keep])
    return pd.concat(blocks, ignore_index=True)


def deprivation_rows(pupils: pd.DataFrame, ids: np.ndarray, local_authority: str) -> pd.DataFrame:
    idaci = pd.Series(np.round(pupils["idaci"].to_numpy(), 4))
    frame = pd.DataFrame(
        {
            PSEUDO_ID: ids,
            "HomeArea": local_authority,
            "SchoolArea": local_authority,
            "DeprivationScore": idaci,
            "DeprivationDecile": np.ceil(idaci.rank(pct=True) * 10).astype(int),
        }
    )
    return frame[PERSONAL_DATA_DEPRIVATION]
