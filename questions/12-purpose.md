# Question 12: "I gave it access for the letters. Why was it looking up who's in care?"

**Open question.** No eval cases and no required design.

**The problem.** Every mandate carries a `purpose` (by default "Pupil-data lookups for school SCH01"). Nothing reads
it. A call that is in scope is allowed whatever it is for. An agent that has been misled, by a bad instruction or
by text in something it read, can spend a valid mandate on a job the person never asked for, and the gateway
cannot tell the difference.

**Worth working out:**

- Can a purpose be something the gateway checks, not a sentence? What would "absence letters" allow that
  "safeguarding review" would not: tools, columns, pupils, a number of calls?
- The gateway sees calls, not reasons. Is anything the agent says about why it is calling worth trusting, when the
  agent is the thing you do not trust?
- Is one short, narrow mandate per job better than one long, wide mandate per agent? What does that cost the person
  who has to grant them?

**What to show:** two mandates for one school with different purposes, one request that is allowed under one purpose
and denied under the other, and one sentence on what is still unresolved.
