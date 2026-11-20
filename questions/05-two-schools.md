# Question 5: "I've given it Brookmere too now. Look up their spring census."

This time the issuer really did grant a second school, as a second `search` entry in the scope rather than a wider
first one. The gateway uses the first scope entry that lists the tool and never tries the next one, so `SCH02` is
refused.

**Cases** (`BUILD` in `gateway/eval.py`, mandate `eval_pack/two_schools.jwt`): searches in `SCH01` and `SCH02` must be
allowed, and a search in `SCH03` must still be denied.

**One way:** in `check_request` (`gateway/lib/gateway_verify.py`), allow the call if *any* entry that lists the tool
accepts every constrained argument. Deny with the most useful reason when none does.

**Think about:** two entries that each constrain a different argument. Can a request mix and match, taking `urn`
from one and `path` from the other?
