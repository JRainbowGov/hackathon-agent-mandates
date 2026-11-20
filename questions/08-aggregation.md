# Question 8: "How many pupils in care does each school have, split by ethnic group?"

**Open question.** No eval cases and no required design.

**The problem.** The answer is only counts, but a count of one in-care pupil of one ethnic group at one school
identifies that child. Whether an answer is safe depends on the result, not on the table it came from. The gateway
only looks at the request.

**Worth working out:**

- Do you check before the call (refuse risky `group_by` combinations), after it (suppress small counts), or both?
- Who sets the smallest count that is safe to release, and where does that setting live?
- Can two answers that are each safe be subtracted to recover a small count?

**What to show:** a counts mandate, a count that is released, a count that is refused or suppressed, and one sentence
on what is still unresolved.
