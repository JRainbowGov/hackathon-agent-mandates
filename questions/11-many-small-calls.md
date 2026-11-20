# Question 11: "Go through Elmwood's Year 11s one at a time and note who's on free school meals."

**Open question.** No eval cases and no required design.

**The problem.** The gateway decides each call on its own. The only thing it remembers between calls is which nonces
it has seen. Question 3 stops one call returning the whole school, but an agent that searches for one pupil at a
time ends up holding the same data, and every one of those calls is allowed. The same applies to counts: two answers
that are each safe to release can be subtracted to find one pupil.

**Worth working out:**

- What does the gateway need to remember, and against what: the mandate, the agent key, or the person?
- What is the limit counted in: calls, rows, or distinct pupils? What does an ordinary day's work look like, so that
  the limit does not stop it?
- When the limit is reached, does the gateway refuse, slow down, or ask the person?
- An agent with two mandates, or a helper agent from question 7, has two budgets. Should it?

**What to show:** an Elmwood mandate, a run of calls that is allowed, the call where the gateway stops the run, and
one sentence on what is still unresolved.
