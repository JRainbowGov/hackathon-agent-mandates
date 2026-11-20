# Question 14: "I gave it too much yesterday. Take it back, and tell me what it saw."

**Open question.** No eval cases and no required design.

**The problem.** Revoking a mandate stops the next call. It does nothing about what the agent has already been
sent, and the starter gateway keeps no record of its decisions (`tools_call` in `gateway/main.py` marks where one
would go). The administrator cannot find out what their agent took, so they cannot tell anyone whose data it was.

**Worth working out:**

- What goes in the record: the decision, the arguments, the rows returned, or a summary of them?
- A record of everything an agent saw is itself a copy of the sensitive data. Who may read it?
- Can whoever runs the gateway change or delete an entry afterwards? How would anyone find out?
- What can a person who is not technical read from it?

**What to show:** a mandate, the requests made with it before it was revoked, the record the administrator reads
afterwards, and one sentence on what is still unresolved.
