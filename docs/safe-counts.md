# Safe counts: question 8

OpenSpec change `add-safe-counts`. `pupil-data.aggregate` counts census rows and suppresses nothing, so a count can
name a child. The gateway now decides what a count may say, for every mandate.

- **Before forwarding,** it refuses:
  - pupil identifier columns (`Psuedo ID`, `DisplayName`) in `group_by`, `where` or `measure`;
  - level-4 columns (`Ethnicity`, `InCareAtCurrentSchool`) unless the mandate has `clearance: 4`;
  - more than 2 `group_by` columns;
  - `where` on level-3 or level-4 columns;
  - for a mandate with no `clearance`, `group_by` above the claim-less level (2 by default, as `search` strips it).
    Its `measure` may still be level 3, so school-level free school meal numbers keep working.

  The reasons are `COUNT_COLUMN_REFUSED` and `COUNT_TOO_FINE`.
- **What it releases:**
  - `total` and `count` are numbers of distinct **pupils**, not census rows. Each pupil has up to 5 rows, one per term.
  - Groups with fewer than 10 pupils are dropped and reported only as `{"suppressed_groups": N}`.
  - A `count` is `null` when it, or `total - count`, is between 0 and 4. Zero is hidden too: otherwise `0` against
    `null` says whether a lone pupil is inside a filter, and a few overlapping filters name them.
  - Everything is rounded to the nearest 5.
- **A mandate can be stricter, not looser:** `--claims '{"counts": {"k": 20}}'` raises the minimum group size.
  Values below 10 are ignored.
- **The gateway works out pupils itself.** It sends the tool the same query grouped by pupil too, and folds the answer.
  Those per-pupil rows never leave the gateway.

## The mandates

```bash
uv run python -m gateway.cli issue --agent-key agent2.pem -o counts.jwt --purpose "School-level counts" \
  --scope '[{"server": "pupil-data", "tools": ["aggregate"], "constraints": {"table": ["personal_data_school_census"]}}]'
uv run python -m gateway.cli issue --agent-key agent2.pem -o counts4.jwt --purpose "Safeguarding counts" \
  --claims '{"clearance": 4}' \
  --scope '[{"server": "pupil-data", "tools": ["aggregate"], "constraints": {"table": ["personal_data_school_census"]}}]'
call() { m=$1; shift; uv run python -m gateway.cli call --mandate "$m" --agent-key agent2.pem --tool aggregate --args "$1"; }
```

## A count that is released

```bash
call counts.jwt '{"table": "personal_data_school_census", "group_by": ["URN"], "measure": "FSMeligible"}'
# 200 ALLOW IN_SCOPE
# [{"URN": "SCH01", "total": 125, "count": 25}, {"URN": "SCH02", "total": 125, "count": 15}, ...]  (12 schools)
```

The audit trail scores this at level 3, the level of `FSMeligible`.

## The leaks it closes

The flag pupil's ethnicity, and every pupil listed, both worked through the starter gateway:

```bash
call counts4.jwt '{"table": "personal_data_school_census", "group_by": ["Ethnicity", "URN"], "measure": "FSMeligible",
                   "where": {"Psuedo ID": "P0011"}}'
# 403 DENY COUNT_COLUMN_REFUSED  Psuedo ID
call counts4.jwt '{"table": "personal_data_school_census", "group_by": ["Psuedo ID", "Ethnicity", "URN"],
                   "measure": "FSMeligible"}'
# 403 DENY COUNT_COLUMN_REFUSED  Psuedo ID
call counts.jwt  '{"table": "personal_data_school_census", "group_by": ["URN", "Ethnicity"], "measure": "FSMeligible"}'
# 403 DENY COUNT_COLUMN_REFUSED  Ethnicity   (no clearance 4)
```

## A count that is hidden

Greystone (`SCH07`) has exactly one pupil in care:

```bash
call counts4.jwt '{"table": "personal_data_school_census", "group_by": ["URN"], "measure": "InCareAtCurrentSchool"}'
# {"URN": "SCH02", "total": 125, "count": null}
# {"URN": "SCH07", "total": 110, "count": null}
```

SCH02 has none in care and SCH07 has one, and the two answers are the same. Filtering SCH07 by gender, year or enrolment
status gives `null` every time, so the filters can't narrow down who it is (they did while zero was exact). Grouping by school and ethnicity at clearance 4 releases 30 groups and reports
`{"suppressed_groups": 46}` for the rest.

## Still unresolved

- **Differencing isn't fully closed.** Rounding to 5, hidden 0 to 4 and the column rules turn the difference between
  two answers into a range, but many queries over larger groups can still narrow it. Repeated filtered counts raise
  `ALERT_COUNTS_NARROWING`; a `calls` budget or a `rate` on the scope entry is the hard limit.
- **The answer's meaning changed** from census rows to pupils. Anyone comparing with the old numbers will see different
  values.
- **The tool grants from the scope-requests change must allow the extra pupil column** on the gateway's own call.
