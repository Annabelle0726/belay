# PR #9 / issue #18: strict classifier verdicts

Classifier responses require both fields, a real boolean flag, and a finite
numeric confidence between zero and one. Missing fields, strings, booleans used
as confidence, nonfinite/out-of-range values and nonobjects yield bounded
`malformed` evidence. They never become successful `safe` verification.

The optional guard retains its existing fail-open availability policy: malformed
classification permits tutoring to continue through deterministic governance,
while its trace explicitly says verification was malformed. This does not skip a
required governance check or redefine a failure as a successful classification.
No raw input, model response or exception text enters classification diagnostics.
The dedicated configured sovereign client is preserved; automatic SDK retries
are disabled. Endpoint deployment/trust is an operator obligation, not inferred
from a URL's name. No live classifier/model request was made during validation.

Tests exercise invalid outputs through peer/control orchestration, check the
content-free trace and downstream governance, and retain hosted-provider refusal.
Full database/quality outcomes are recorded in the final repair summary. Existing
unsigned history was preserved; new commits carry Annabelle's DCO sign-off.


## Recorded validation

Full validation source: `8737083afa729199bfa0e8565ca44f4b83de0fd0`.

| Gate | Passed | Failed/errors | Skipped |
| --- | --- | --- | --- |
| sqlite | 428 | 0 | 7 |
| postgres | 428 | 0 | 7 |

Ruff lint, format check and configured mypy passed for that full-run source. Seven full-suite skips are the opt-in live evaluation and unavailable sibling-contract schema cases. No paid model request was used.

Existing unsigned commits in the original PR history: 8. New repair/documentation commits are signed off. The old history has not been rewritten. The repair head has not been pushed, merged, or run through hosted CI. No command to start, stop or restart the actual API/worker service was issued. Live serving state was not revalidated.
