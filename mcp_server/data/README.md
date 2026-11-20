# Example datasets

Fake data for the access-mandate hackathon. Every pupil, name and school is invented.

## What is in `synthetic/`

- `synthetic_manifest.json` — row counts plus a fake 4-level PII classification per table
  (1 Public, 2 Basic PII, 3 Sensitive PII, 4 Special Category): schools 1, display names and deprivation 2,
  census 4 because it carries ethnic group.

If brokenm, regenerate with `make synth`. Settings, including the levels (under `classification`), live in `synth/synth.yaml`.

### Tables and how they connect

| File (`synthetic_*.csv`)      | Rows  | One row per                  | Key         | Connects to           | PII level |
| ----------------------------- | ----- | ---------------------------- | ----------- | --------------------- | --------- |
| `schools`                     | 12    | school                       | `URN`       |                       | 1         |
| `personal_data_school_census` | 7,449 | pupil per term (4 or 5 each) | `Psuedo ID` | `schools` by `URN`    | 4         |
| `personal_data_deprivation`   | 1,500 | pupil                        | `Psuedo ID` | census by `Psuedo ID` | 2         |
| `display_names`               | 1,500 | pupil                        | `Psuedo ID` | census by `Psuedo ID` | 2         |

```text
schools ──URN──< school_census >──Psuedo ID──┬── deprivation
                                             └── display_names
```

- `URN` is `SCH01` to `SCH12`. `Psuedo ID` is `P0001` to `P1500`: three Year 11 cohorts of 500
  (2021/22 `P0001`–`P0500`, 2022/23 `P0501`–`P1000`, 2023/24 `P1001`–`P1500`).
- Only the census carries `URN`, so it is the only route from a pupil's name or deprivation score to their school.
  Each pupil is at one school throughout.

## What the MCP server does with it

- `search(query, urn)` — text search over school census rows, optionally limited to one school.
- `get(path, limit)` — one file: JSON parsed, or CSV rows (default 100).
- `aggregate(table, group_by, measure, where)` — counts per group, with no small-cell suppression
  (see `hackathon/aggregation`).

Your gateway is what enforces the mandate: one scoped to
`{"server": "pupil-data", "constraints": {"urn": ["SCH01"]}}` should only ever see that school's pupils.

## See it

```bash
head -3 mcp_server/data/synthetic/synthetic_personal_data_school_census.csv  # the raw records
curl -s localhost:8080/mcp-tools | jq '.[].name'                   # the tools the MCP server exposes, no auth
uv run python -m gateway.cli call --mandate gateway/state/mandate.jwt --agent-key gateway/state/agent.pem \
    --tool search --args '{"query": "P0004", "urn": "SCH01"}'  # through the gateway: ALLOW
uv run python -m gateway.cli call --mandate gateway/state/mandate.jwt --agent-key gateway/state/agent.pem \
    --tool get --args '{"path": "synthetic/synthetic_display_names.csv"}'  # every pupil's name: DENY
```
