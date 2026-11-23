"""schools: level 1. The schools list and the classification table, nothing personal."""

from fastmcp import FastMCP

from data_slices import reader

LEVEL = 1
KEYS = ("URN", "SchoolName", "SchoolLA")

mcp = FastMCP("schools")


@mcp.tool
def list() -> list[dict]:  # noqa: A001  (the tool name agents see is "list")
    """Every school: URN, name and local authority."""
    return [reader.project(r, KEYS) for r in reader.rows("schools", LEVEL)]


@mcp.tool
def classification() -> dict:
    """The data level of every table and column: 1 public, 2 basic PII, 3 sensitive PII, 4 special category."""
    return reader.classification()
