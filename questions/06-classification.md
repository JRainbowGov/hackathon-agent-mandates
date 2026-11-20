# Question 6: "Send me the full records for Castleton's pupils, ethnicity and care status included."

**Open question.** No eval cases and no required design.

**The problem.** A mandate says which tools and arguments an agent may use. It says nothing about how sensitive the
data behind them is. The census file holds ethnicity, free school meals and care status, which is special category
data (sensitivity 4 in `mcp_server/data/synthetic/synthetic_manifest.json`). The gateway keeps it from the agent today only
because the `urn` constraint happens to block `get`.

**Worth working out:**

- Where does a sensitivity label live: with the data, in the mandate, or in the gateway?
- What does a mandate with no clearance get?
- One call can touch data at two sensitivities. Which one decides?

**What to show:** two Castleton mandates at different clearances, one request that is allowed under the higher
clearance and denied under the lower, and one sentence on what is still unresolved.
