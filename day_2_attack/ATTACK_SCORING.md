# Attack scoring (Day 2 afternoon)

Your score is how sensitive the data is that you get out of another team's
gateway with the two mandates they give you, plus bonuses for breaking the gateway itself.

**The default mandate**: `search` at Ashfield Academy (`SCH01`) only, and
`get` on the schools file and the manifest. Every scoring flag below is outside it. Every team hands out the same one.

**The feature mandate**: the defending team's own design, from the open question they took on Day 1 (a clearance, a
child mandate, a purpose, a limit). It is the thing they built, so it is the thing to attack. Each comes with a note
saying what it allows and what it should refuse.

## Handing out mandates

Each defending team issues one mandate per attacking team, from the issuer state its deployed gateway trusts.

1. **Attackers:** make one key and post the public half where every team can see it. Keep `attack.pem` to yourself.

   ```bash
   uv run python -m gateway.cli keygen -o attack.pem > <your-team>.jwk
   ```

2. **Defenders:** put every other team's `<team>.jwk` in `day_2_attack/keys/`, then run `make attack_mandates`. It
   writes `day_2_attack/mandates/<team>.jwt` (the mandate above, for 24 hours) and prints each status idx, so you
   can revoke one team without the others.

3. **Defenders, the feature mandate:** start from the mandate you showed at the Day 1 check-in. If your feature is a
   scope or a claim, put each in a JSON file and run

   ```bash
   make attack_mandates FEATURE_SCOPE=feature_scope.json FEATURE_CLAIMS=feature_claims.json
   ```

   It writes `day_2_attack/mandates/<team>.feature.jwt` beside each default mandate. If your feature is issued some
   other way (a child mandate, a purpose), issue it your own way under the same names. Then post the mandates folder
   and a note: what the feature mandate allows, with at least one request it allows, and what it should refuse.

4. **Attackers:** call with `--mandate <their mandate for you> --agent-key attack.pem --url <their gateway>`.

## Capture the Data flags

The levels are the four in [the manifest](../mcp_server/data/synthetic/synthetic_manifest.json). 

The flag pupil is **`P0011`**, at Dunmore Community College (`SCH04`).

| Level | Classification | Flag: the gateway's response contains | Comes from | Points |
| --- | --- | --- | --- | --- |
| 1 | Public information | The name of `SCH04`: `Dunmore Community College` | schools | 0 |
| 2 | Basic PII | `P0011`'s name, `Zara Okafor`, or their deprivation score, `0.2505` | display names, deprivation | 10 |
| 3 | Sensitive PII | `P0011`'s census row, showing their school (`SCH04`) or `FSMeligible` | census | 20 |
| 4 | Special category | `P0011`'s `Ethnicity` (`ASIA`) or `InCareAtCurrentSchool` | census | 40 |
| 4, named | Special category tied to a name | Who is the one pupil in care at Greystone School (`SCH07`)? Show their in-care census row (`P0586`) and their name (`Mason Owusu`) | census and display names | 60 |

- **Score each mandate separately.** On each target, score the highest row you reach with the default mandate, plus
  the highest you reach with the feature mandate.
- **A flag only counts if it is outside the mandate you used.** For the feature mandate, that is its scope and the
  defender's note: data the note says it allows scores nothing.
- **Within one mandate, score the highest row, not the sum.** A full census row for `P0011` is 40, not
  20 + 40. If the target strips the level 4 columns, the same attack is worth 20. 
- **Level 1 is in your mandate.** It scores nothing. Use it to check your mandate works before you start.
- **Counts can score.** An `aggregate` answer counts if it pins the fact to the flag pupil, for example a group of
  one.

## Gateway breaks

Bonuses, added on top of the data score. Each is scored once per target, whichever mandate you used.

| Break | What it means | Points |
| --- | --- | --- |
| Keys | A response contains the target's issuer private key | 50 |
| Forged mandate | The target accepts a mandate its issuer never signed for you: edited claims, an issuer it should not trust, or one you got the target to mint for you | 30 |
| Dead mandate | The target accepts a mandate that has expired or been revoked | 15 |
| No key | The target accepts a call that is not freshly signed by the mandate's key: a bad signature, a replayed request, a stale timestamp | 15 |
| Bulk | More than 100 different pupils outside your mandate in the responses you submit | 10 |
| Unseen | You landed a data flag and the target team cannot find it in their own records within 5 minutes | 10 |
| Crash | One request makes the gateway answer `500` or stop answering | 5 |

## Claiming points

- **Post the request you sent and the response you got**, with the target team's name.
- **The response is the proof.** Every team has the data in their own repo, so knowing a flag's value proves
  nothing. A data flag needs a `200` from the target's URL with `"decision": "ALLOW"` and the flag in the result.
- **Breaks** need the accepted request and one line on why it should have been refused. For Crash, the `500`.
- The organisers settle disputes.

## Out of bounds

- Calling a target's MCP server directly. An attack only counts through the gateway.
- Flooding. Crash is one request, not a thousand.
- Anything that is not the target's posted gateway URL: their laptops, their repo, their cloud account, their
  people.

## Defending

**Clean sheet: 30 points** if no team scores level 2 or above on your gateway with the default mandate.

**Feature held: 20 points** if no team scores level 2 or above on your gateway with your feature mandate. It needs a
feature mandate posted by the end of Day 2 morning that allows at least one real request for its job: a mandate that
allows nothing has not earned it.

Both only count if questions 0 to 5 all pass on your deployed URL at the end (`GATEWAY_URL=<your url> make eval_run`).
A gateway that refuses everything is no use to the school administrator, and one that still lets the whole school out
in one call (question 3) has not earned a clean sheet.

## Tally

One row per gateway you attacked. Your team's score is the sum of the totals, plus the clean sheet and feature held.

| Target | Data, default mandate | Data, feature mandate | Breaks | Total |
| --- | --- | --- | --- | --- |
| *Team A* | *40 (level 4)* | *20 (level 3)* | *30 (forged mandate) + 5 (crash)* | *95* |
|  |  |  |  |  |
|  |  |  |  |  |
| Clean sheet |  |  |  |  |
| Feature held |  |  |  |  |
| **Team score** |  |  |  |
