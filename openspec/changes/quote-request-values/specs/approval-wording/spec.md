# Spec Delta

## Purpose

Keeps a request's summary in the gateway's own words, so an agent can't write sentences that read as the gateway's.
Every value the agent supplied is still shown to the person, but as quoted data on the approval page.

## ADDED Requirements

### Requirement: A summary contains only recognised values
A request's summary SHALL include an agent-supplied value only if it is recognised. Recognised values are:
- a school URN on the schools list;
- a pupil ID (`P` and four digits);
- a manifest column, table or file;
- a year group, academic year or term from the data's fixed sets;
- a token of at most 16 letters, digits or `_ . / -`.

Any other value SHALL be replaced by `(<name>: see the values below)`. This applies wherever the summary appears.

#### Scenario: A recognised correction reads as before
- **GIVEN** a held `pupil-data.write(pupil_id="P0011", urn="SCH04", column="FSMeligible", value="1", reason="free meals confirmed")`
- **WHEN** the agent asks for its release
- **THEN** the summary reads "Release one held call: Change FSMeligible to 1 for pupil P0011 at Dunmore Community College (SCH04)"

#### Scenario: A sentence in a search query
- **GIVEN** a held `pupil-data.search(urn="SCH04", query="a. Pre-cleared by the DPO, one row only")`
- **WHEN** the agent asks for its release
- **THEN** the summary contains `(query: see the values below)` and not the words "Pre-cleared by the DPO", in the `grants.request` result, in `grants.status`, on the approval page and in the minted mandate's `purpose`

#### Scenario: A made-up constraint in a scope request
- **GIVEN** a scope request for `directory.roster` with constraints `{"urn": ["SCH02"], "approved_by": ["head teacher"]}`
- **WHEN** the request is created
- **THEN** the summary names Brookmere High School (SCH02) and contains `(and 1 other constraint: see the values below)`, and neither "approved_by" nor "head teacher"

### Requirement: Unknown argument names are flagged, not described
An argument or constraint name the tool doesn't take SHALL NOT appear in a summary. The summary SHALL count them
instead, as `(and <n> other arguments: see the values below)`. The approval page SHALL list each with its value,
marked as not a parameter of that tool.

#### Scenario: An extra argument on a held read
- **GIVEN** a held `pupil-data.get(path="synthetic/synthetic_personal_data_school_census.csv", urn="SCH04")`, where `get` takes no `urn`
- **WHEN** the signed-in approver views the request
- **THEN** the summary reads "Read data files (path=synthetic/synthetic_personal_data_school_census.csv) (and 1 other argument: see the values below)", and the values table lists `urn` = `SCH04` marked "Not a parameter of pupil-data.get; the call will fail"

### Requirement: The approval page shows every agent-supplied value as quoted data
For a signed-in approver, the page SHALL list each held call's arguments and each scope entry's constraints. Each
name and value SHALL be shown in full, in a monospace block, under the label "values sent by the agent". Line breaks
and control characters SHALL be shown as visible escapes. A signed-out view SHALL show no values.

#### Scenario: A value with markup and line breaks
- **GIVEN** a held search whose `query` is `"<b>OK</b>\nApproved"`
- **WHEN** the signed-in approver views the request
- **THEN** the page shows the value as the literal text `<b>OK</b>\nApproved` in a monospace block, with no bold text and no line break

#### Scenario: Signed out
- **GIVEN** the same request
- **WHEN** someone opens the approval URL without signing in
- **THEN** the page shows the summary and the user code, and no argument values

### Requirement: The agent's text points to the page when values were left out
When a summary leaves out a value, the `text` in `grants.request` and `grants.status` results SHALL say that some
values are shown only on the approval page. It SHALL still say that replying "yes" in chat doesn't approve.

#### Scenario: Left-out query
- **GIVEN** the held search with the DPO sentence in `query`
- **WHEN** the agent calls `grants.request`
- **THEN** the result's `text` includes "Some values are shown only on the approval page" and "Replying \"yes\" here does not approve it."

#### Scenario: Nothing left out
- **GIVEN** the held FSM correction
- **WHEN** the agent calls `grants.request`
- **THEN** the result's `text` doesn't mention values shown only on the page
