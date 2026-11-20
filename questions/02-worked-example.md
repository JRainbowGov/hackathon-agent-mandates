# Question 2: "While you're in there, check the school next door, and get me everyone's names."

**Worked example.** The starter gateway already passes this question, so there is nothing to fix. This page shows
what a demonstration looks like: a mandate, a request it allows, a request it denies, and what is still unresolved.
Use a similiar layout for whatever your team shows, at the Day 1 check-in and on the open questions.

Show the decoded claims and the commands, not a `.jwt` file. Each laptop is its own issuer and mandates expire, so
a token copied from here would fail on your gateway. Everything below runs after `make hack`.

## The mandate

The default mandate from `make gateway_issue`: `search` at Ashfield (`SCH01`) only, and `get` on the two files that
hold no pupil data. Decode it with:

```bash
uv run python -m gateway.cli decode gateway/state/mandate.jwt
```

The main claims for this question (the rest are the issuer, the dates, the agent key and the revocation index):

```json
{
  "delegator": {"principal": "officer:jsmith", "org": "school:SCH01", "authority": "hackathon"},
  "purpose": "Pupil-data lookups for school SCH01",
  "scope": [
    {"server": "pupil-data", "tools": ["search"], "constraints": {"urn": ["SCH01"]}},
    {"server": "pupil-data", "tools": ["get"],
     "constraints": {"path": ["synthetic/synthetic_schools.csv", "synthetic/synthetic_manifest.json"]}}
  ],
  "deny": ["*.write", "pii.*"]
}
```

## A request it allows

One pupil at Ashfield:

```bash
uv run python -m gateway.cli call --mandate gateway/state/mandate.jwt --agent-key gateway/state/agent.pem \
  --tool search --args '{"query": "P0004", "urn": "SCH01", "limit": 1}'
```

```text
200
{
  "decision": {"decision": "ALLOW", "reason_code": "IN_SCOPE", "detail": "", ...},
  "result": [{"Psuedo ID": "P0004", "AcademicYear": "2020/21", "CensusTerm": "AUT", "URN": "SCH01", ...}]
}
```

## Requests it denies

"Check the school next door." The same tool, at Brookmere (`SCH02`):

```bash
uv run python -m gateway.cli call --mandate gateway/state/mandate.jwt --agent-key gateway/state/agent.pem \
  --tool search --args '{"query": "SPR", "urn": "SCH02"}'
```

```text
403
{"decision": {"decision": "DENY", "reason_code": "CONSTRAINT_VIOLATED", "detail": "urn='SCH02'", ...}}
```

"Get me everyone's names." An allowed tool, on a file the mandate does not list:

```bash
uv run python -m gateway.cli call --mandate gateway/state/mandate.jwt --agent-key gateway/state/agent.pem \
  --tool get --args '{"path": "synthetic/synthetic_display_names.csv"}'
```

```text
403
{"decision": {"decision": "DENY", "reason_code": "CONSTRAINT_VIOLATED",
              "detail": "path='synthetic/synthetic_display_names.csv'", ...}}
```

## Still unresolved

The mandate limits which school, not how much: an empty `query` is in scope and returns every Ashfield row. That is
[question 3](03-bulk-export.md).

The eval fires more cases for this question than the two above: the question 2 rows of `INVALID` in
`gateway/eval.py`.
