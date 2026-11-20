# Question 4: "The file's at ./synthetic/synthetic_schools.csv, open that."

Constraints compare strings exactly. `./synthetic/synthetic_schools.csv` and `synthetic//synthetic_schools.csv` are
the allowed file, and the gateway refuses both. That is safe, but it blocks a legitimate request.

**Cases** (`BUILD` in `gateway/eval.py`): both spellings must be allowed, and
`synthetic/../synthetic/synthetic_display_names.csv` (every pupil's name) must still be denied.

**One way:** normalise `path` before comparing it (`posixpath.normpath`), and refuse anything that still starts with
`..` or `/`. The MCP server resolves paths itself (`get` in `mcp_server/api/routes_mcp.py`), so whatever the gateway
compares has to name the same file the server will open.

**Think about:** an allowed folder rather than an allowed file (`synthetic/*.json`). What can a glob match that you
did not mean?
