# Design

## Context

See proposal.md for why. Summaries are built in `gateway/lib/grant_words.py`:
- `entry_words` for scope entries;
- `action_words` for held calls.

They're stored on the request at creation (`requested.summary`, `public_summary` in `issuer/app.py`) and reused by:
- `agent_view` and `summary_of`;
- `_with_next` (the agent's `text`, in `gateway/lib/grants.py`);
- `mint_for` (`purpose`);
- the approval page (`ApprovalRequest.svelte`, which renders `summary`, `held_action` and `held_actions` as Svelte
  text, so nothing is parsed as HTML).

Tool parameter names are known from the MCP servers' schemas, but the gateway doesn't keep them.

## Goals / Non-Goals

**Goals:**
- Summaries are made only from gateway vocabulary and recognised values.
- The person can still see every value, clearly marked as coming from the agent.

**Non-Goals:**
- Deciding whether a value is safe. No denylist of words, no LLM check.

## Decisions

**1. Allowlist values; don't escape or quote them inline.**
- `grant_words` gets one function, `shown(name, value, server, tool) -> str | None`. It returns the inline form for
  a recognised value (a school name for a URN, the value itself otherwise) and `None` for anything else, which then
  becomes `(<name>: see the values below)`.
- **Alternative considered:** keep every value but wrap it in quotes. Rejected:
  - the agent can put quote characters in the value;
  - chat clients render markdown, so the `text` could still be made to look like something else;
  - a short allowlist of shapes can be tested.

**2. Known parameters per tool, kept in the gateway.**
- A table `TOOL_PARAMS` in `grant_words.py` next to `TOOL_WORDS`, for example `("pupil-data", "get"): {"path",
  "limit"}`.
- **Alternative considered:** fetch the schemas from the MCP servers at startup (as `/describe` does). Rejected:
  - it adds a network dependency to building a sentence;
  - the words table is already hand-kept for the same tools.
- A unit test compares `TOOL_PARAMS` with the in-process MCP server's tool schemas, so drift is caught in CI.

**3. Structured values beside the words.**
- The issuer stores `requested.values` at creation, as a list per held call or scope entry of `{name, value, known}`,
  where `known` is whether the tool takes that name.
- `request_view` returns `values` only to the signed-in principal, as it already does for `held_action`.
- The page renders each value with `JSON.stringify(value)` minus the outer quotes, inside `<code>`. That shows `\n`,
  `\t`, `\u0000` and so on as escapes, and Svelte text keeps markup literal.

**4. Where it runs.** All of it runs when the request is created (issuer `create_request`, and the gateway for
`grants.self` and `grants.check`). No change to `check_request` or the call path, so no new decision path and no new
reason code.

**Failure mode:** a value the rule can't classify (an unexpected type, a nested object) is treated as not recognised
and left out of the summary. It is never put in inline.

**Day 2 (ATTACK_SCORING.md):** closes nothing in the scoring directly, since no data flag comes from wording alone. It
removes the step that gets a person to approve a request they wouldn't approve if they read it plainly, for example
a held call worded as "one row only".

## Risks / Trade-offs

- **Summaries get vaguer for long legitimate values**, such as a `write` `reason` or a long query. Mitigation: the
  page shows the full value right below, and the pointer names which argument to look at.
- **`TOOL_PARAMS` drifts from the servers.** Mitigation: the schema test (decision 2).
- **Requests stored before this change keep their old summaries.** Mitigation: pending requests expire within their
  TTL. Old rows without `values` render as before.

## Migration Plan

Rebuild the gateway, issuer and frontend containers. No data migration. Rollback is redeploying the previous images.
