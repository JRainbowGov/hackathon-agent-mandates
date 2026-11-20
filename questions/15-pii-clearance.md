# Question 15: "This one's only doing the newsletter. It doesn't need anything personal."

**Open question.** No eval cases and no required design.

**The problem.** A mandate says which tools and arguments an agent may use. It has no idea how sensitive the data is.
The data is already labelled on a four-level scale, per table and per column: 1 public, 2 basic PII, 3 sensitive
PII, 4 special category. The `classification` MCP tool returns the labels. Nothing in a mandate says which level an
agent is cleared to, so a newsletter agent with `search` gets whole census rows, ethnicity and care status included.

**Worth working out:**

- What does a clearance claim in the mandate look like, and does the issuer or the gateway decide what it covers?
- Does the gateway refuse a call that could touch data above the clearance, or allow it and strip those columns from
  the result? Which one can an agent get round?
- `search` returns rows from a level 3 table with level 4 columns in it. Which label decides: the table or the column?
- Where does the gateway read the labels from, and what happens when the labels change after a mandate is issued?

**What to show:** a newsletter mandate at clearance 1 and a counts mandate at clearance 3, a request each one allows,
a request each one denies, and one sentence on what is still unresolved.
