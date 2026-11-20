# Question 3: "Just pull everything for Brookmere, I'll sort through it."

The mandate limits *which school*, not *how much*. `search` with an empty `query` matches every row, and `limit` is
not constrained, so one call returns all 630 census rows for Brookmere (`SCH02`), free school meals and in-care flags
included. The same holds at Ashfield (617 rows) under the default mandate. Every check passes: right tool, right school.

**Cases** (`BUILD` in `gateway/eval.py`): an empty query with `limit: 1000`, and an empty query with no limit, must
both be denied. Question 0 must still pass, and it includes searches with no `limit` at all.

