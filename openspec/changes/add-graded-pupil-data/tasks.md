## 1. Clearance

- [x] 1.1 Make `pupil-data` graded in `check_clearance` (any clearance 1 to 4 allowed) and refuse `pupil`, `roster`, `draft` and `write` without a clearance (`CLEARANCE_MISSING`); verify unit tests and the existing clearance tests
- [x] 1.2 Hold `pupil-data` `search`, `pupil` and census `get` at clearance 4 with `SPECIAL_CATEGORY`, released once by pre-approval; verify the ethnicity-needs-a-person and approved-once scenarios

## 2. Stripping

- [x] 2.1 Strip `pupil-data` results above the clearance at the gateway before release (the MCP server already does it via the tool grant); verify the clearance-2 and clearance-3 scenarios through the gateway

## 3. Final checks

- [x] 3.1 Update tests that relied on no-clearance person-level tools or clearance 4 reads; `make test`, `make lint`, `make eval_run` 32/32
- [x] 3.2 Live: the P0050 call without clearance is refused, at clearance 2 it returns no sensitive fields
