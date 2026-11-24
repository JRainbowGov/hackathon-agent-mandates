"""Graded pupil-data (OpenSpec add-graded-pupil-data): a mandate's clearance decides which columns it receives.

    special_category_read(server, tool, arguments, claims)   a clearance-4 pupil-data call that returns level-4
                                                             columns: held for a person's approval
    strip(data, level)                                       a result without columns above `level`

The MCP server strips the same columns through the tool grant's level; the gateway strips again before release,
so a result never leaves with more than the mandate's clearance even if the server didn't.
"""

from __future__ import annotations

import posixpath
from typing import Any

from .audit import _is_row, column_level

GRADED_SERVER = "pupil-data"
CENSUS_FILE = "synthetic/synthetic_personal_data_school_census.csv"
# pupil-data tools whose results include level-4 census columns
SPECIAL_CATEGORY_TOOLS = frozenset({"search", "pupil"})


def _clearance(claims: dict | None) -> int | None:
    clearance = (claims or {}).get("clearance")
    return clearance if type(clearance) is int and 1 <= clearance <= 4 else None  # noqa: PLR2004


def special_category_read(server: str, tool: str, arguments: dict, claims: dict | None) -> bool:
    if server != GRADED_SERVER or _clearance(claims) != 4:  # noqa: PLR2004
        return False
    if tool in SPECIAL_CATEGORY_TOOLS:
        return True
    path = arguments.get("path")
    # any spelling that could open the file: case-insensitive (macOS), any directory prefix
    return tool == "get" and isinstance(path, str) and (
        posixpath.basename(posixpath.normpath(path.replace("\\", "/"))).lower() == posixpath.basename(CENSUS_FILE)
    )


def level_for(server: str, claims: dict | None) -> int | None:
    """The level a graded server's result is stripped to: the clearance, or None (nothing to strip)."""
    clearance = _clearance(claims)
    return clearance if server == GRADED_SERVER and clearance is not None and clearance < 4 else None  # noqa: PLR2004


def _strip_row(row: dict, level: int) -> dict:
    return {k: v for k, v in row.items() if column_level(k) <= level}


def strip(data: Any, level: int) -> Any:
    """Rows (flat dicts) lose every column above `level`; documents (nested JSON) are left as they are."""
    if isinstance(data, list):
        return [_strip_row(r, level) if _is_row(r) else r for r in data]
    if _is_row(data):
        return _strip_row(data, level)
    return data
