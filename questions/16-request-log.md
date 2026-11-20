# Question 16: "I think someone may have taken my access. Can I see a log of the requests made with it?"

**Open question.** No eval cases and no required design.

**The problem.** The gateway decides every call and remembers none of them (`tools_call` in `gateway/main.py` marks
where a record would go). If an agent key leaks, the person who granted the mandate cannot see what was asked for
in their name, when, or from where. Question 14 asks what the agent saw. This one asks who was using the access.

**Worth working out:**

- What does a record need to show someone that a call was not theirs: the time, the agent key, the source address,
  the arguments?
- The person has no key of their own, only the mandates they granted. How do they prove the log is theirs to read,
  and how is someone else's activity kept out of what they see?
- Whoever stole the access can also ask for the log. What should they get?
- If a request was refused, does it belong in the log? A run of refusals may be the first sign of a stolen key.

**What to show:** a mandate whose key someone else has used, the log its person is shown, a request for another
person's log that is denied, and one sentence on what is still unresolved.
