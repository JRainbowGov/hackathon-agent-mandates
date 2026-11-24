# Proposal

## Why

The approval summary is meant to be the gateway's own words, so the person can trust it over the agent's. It isn't.
For a held call, `action_words` puts every argument value into the sentence as written, and so does the generic
`(k=v, …)` form. For a scope request, `entry_words` puts every constraint key and value into a "where … is …" clause.
All of those strings are chosen by the agent. Argument names are too, because the gateway holds a call before the
tool's own argument check runs.

An agent can therefore make the summary say whatever it likes, in the gateway's voice. For example:
- a search `query` of `a. Pre-cleared by the DPO, one row only`;
- a write `value` that reads like an instruction;
- a made-up constraint `{"approved_by": ["head teacher"]}`.

The same summary goes into the `text` the agent is told to show the person in chat, into `grants.status`, and into
the minted mandate's `purpose`.

This was found by reading the code on 24 Nov and hasn't been tried live. It's the main way left to mislead an
approver once the release scope is fixed (`release-only-held-calls`).

Questions **10** (plain words) and **9** (step-up). Layer: scope requests, the approval page.

## What Changes

- **Summaries hold only gateway words and values the gateway recognises.** These are:
  - a known school URN (shown with its name);
  - a pupil ID;
  - a manifest column, table or file;
  - a fixed-vocabulary value (year group, academic year, term);
  - a short plain token: at most 16 characters of letters, digits, `_ . / -`, no spaces.

  Any other value is left out of the sentence and replaced by a pointer: `(query: see the values below)`.
- **Argument names the tool doesn't take never appear in a summary.** They're listed with the values, marked "not a
  parameter of `<tool>`; the call will fail".
- **The signed-in approval page lists every value verbatim, as quoted data.** Each held call, and each scope entry's
  constraints, gets a table of name and value, labelled "values sent by the agent". Each value is shown:
  - in full, in a monospace block;
  - with line breaks and control characters made visible.
- **The agent-facing `text` says values are on the page.** When anything was left out of the summary, `text` says
  "some values are shown only on the approval page".

Requests whose values are all recognised get the same summary as today, for example the held FSM correction in the
existing spec. Mandates aren't touched, and question 0 keeps passing.

## Capabilities

### New Capabilities
- `approval-wording`: what may appear in a request's summary, and how agent-supplied values are shown to the person.

### Modified Capabilities
None in main specs. `scope-requests` (add-scope-requests) is still a pending change. Its "The approval page shows
what will be granted, not what the agent says" requirement is extended by this one, and its scenarios still hold.

## Non-goals

- **Judging whether a value is harmful.** The rule is about where values are shown, not about filtering them.
- **Changing the agent's `reason` field.** It's already shown as plain text under the agent's-words label.
- **Refusing calls with unknown argument names.** That's the tool's own argument check, or a separate gateway change.

## Impact

- **Changed code:**
  - `gateway/lib/grant_words.py`: the value rule, plus a structured `values` view alongside the words.
  - `issuer/app.py`: `request_view` returns the values, and the agent's `text` gets its note.
  - `gateway/lib/grants.py`: `_with_next`, the `text`.
  - `frontend/src/components/ApprovalRequest.svelte`: the values table. This component is not the demo
    walkthrough.
- **Tests:** `gateway/tests/test_grant_words.py` and `gateway/tests/test_scope_requests.py`.
- **Day 2:** removes the "make the gateway say it" route to an approval on a gateway whose feature is the escalation
  flow.
