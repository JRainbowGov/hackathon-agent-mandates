# Question 9: "Just correct the record yourself."

**Open question.** No eval cases and no required design.

**The problem.** Some calls should wait for a person to approve them. The gateway already returns `202 STEP_UP` for
tools matching `*.write` or `*.draft`: the MCP server's `write` (correct a census field) and `draft` (letters
home) tools. Nothing exists yet to approve a held call, so a held call can never go through. `cli issue` denies
`*.write` by default, so a mandate that allows a write needs `--deny '[]'` (or a narrower deny list).

**Worth working out:**

- Who is asked to approve, and how do they answer?
- How is a held call released exactly once?
- What happens if nobody answers?

**What to show:** a mandate that allows a write, a call that is held and then released by a person, a held call that
nobody approves, and one sentence on what is still unresolved.
