# Tasks

## 1. Recognised values in summaries

- [x] 1.1 Add `TOOL_PARAMS` to `gateway/lib/grant_words.py` and a test that compares it with the in-process MCP server's tool schemas; verify the test passes and fails when a parameter is removed from the table
- [x] 1.2 Add `shown(name, value, server, tool)` (design decision 1) with unit tests in `gateway/tests/test_grant_words.py` for each recognised shape and for spaces, markup, line breaks, long tokens, non-strings and unknown names; verify `pytest gateway/tests/test_grant_words.py`
- [x] 1.3 Use `shown` in `action_words` and `entry_words` so unrecognised values become `(<name>: see the values below)` and unknown names are left out; verify the "recognised correction", "sentence in a search query" and "made-up constraint" scenarios as tests, and that existing grant-words tests still pass

## 2. Values on the approval page

- [x] 2.1 In `issuer/app.py` `create_request`, store `requested.values` (`{name, value, known}` per held call or scope entry) and return it from `request_view` to the signed-in principal only; verify with tests that signed-out views have no `values` and signed-in views do
- [ ] 2.2 (built and `npm run build` passes; not yet viewed on `:8081`, since another session owns the running stack) In `frontend/src/components/ApprovalRequest.svelte`, render a "values sent by the agent" table under each held call or scope entry, values in `<code>` via `JSON.stringify` minus outer quotes, unknown names marked "not a parameter of `<server.tool>`; the call will fail"; verify by viewing a request with `"<b>OK</b>\nApproved"` on `:8081` and checking the demo walkthrough still loads
- [x] 2.3 Document the value rule and the page table in `docs/scope-requests.md` ("What the person sees and does"); verify the doc's example matches a live request

## 3. The agent's text

- [x] 3.1 In `gateway/lib/grants.py` `_with_next`, add "Some values are shown only on the approval page." when the request has left-out values; verify both "agent's text" scenarios as tests in `gateway/tests/test_scope_requests.py`
- [x] 3.2 Check the minted mandate's `purpose` and `grants.status` summary use the new words; verify with a test approving the DPO-query request and decoding the minted mandate

## 4. Integration

- [ ] 4.1 (not run: another session owns the running stack) `make eval_run`: question 0 at 12/12 and no regressions in 1 to 5
- [x] 4.2 `make test`
- [x] 4.3 `make lint`
- [ ] 4.4 (not run: another session owns the running stack) `docker compose up -d --build gateway issuer frontend`, then create the DPO-query held search against `:8082` and check the summary, the agent's `text` and the signed-in page
