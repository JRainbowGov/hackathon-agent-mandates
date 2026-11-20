# Question 13: "I'm leaving at Easter. Priya is taking over my agents."

**Open question.** No eval cases and no required design.

**The problem.** A mandate names the person who granted it (the `delegator` claim), but nothing connects it to
what that person may access. `cli issue --principal` accepts any name. So a mandate can grant more than its person
holds, and when the person leaves or loses a school, every mandate they signed keeps working until it expires.

**Worth working out:**

- Where does the gateway learn what a person may access, and that it has changed?
- How does the gateway know a mandate is no wider than its person? Is that checked when the mandate is issued, on
  every call, or both?
- When a person leaves, do their mandates stop, pause, or pass to their successor? Who decides?
- Priya's access may be narrower than her predecessor's. What happens to the agents she inherits?

**What to show:** mandates granted by two people, a request that is allowed before its person's access changes and
denied after, and one sentence on what is still unresolved.
