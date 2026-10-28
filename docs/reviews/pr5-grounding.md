# PR #5 / issue #15: honest grounding status and reproducible NLP

Grounding distinguishes checked, skipped and unavailable. Missing/unloadable NLP
or failed parsing preserves the response and returns unknown (null) measurements,
not a claim-free successful check. A successfully parsed question with no claims
remains a checked claim-free result. Traces contain bounded statuses, IDs and
counts only, with unknown ungrounded status distinct from false.

Claim citations still work for mixed grounded/ungrounded answers. Citation text
is attached before final deterministic governance. Rewrites are checked again;
remaining leaking prose is replaced with a checked safe fallback or no answer is
released. A safety rewrite invalidates the earlier grounding result rather than
claiming the replacement was checked against the original claims.

Normal `pip install -r backend/requirements.txt` (from the repository root) installs
the pinned spaCy 3.8.16 and official en_core_web_sm 3.8.0 wheel via a nested
requirements file. The container copies that file, and CI verifies offline model
loading after installation. No request path downloads dependencies or a model.
Deployment smoke check: `python -c "import spacy; spacy.load('en_core_web_sm')"`.

Unrelated CORS/injection settings, application imports, shared fixture/DB changes,
distress refactors and seed-script churn were removed. Grounding tests own their
payload helper. Historical DCO metadata is preserved; full validation outcomes
are recorded in the final repair summary. No paid inference was performed.


## Additional missing-verdict protection

A resource-constrained validation run exposed an existing failure path: a runner with no grading verdict could be treated as a checked non-solution. The grader now records verification availability, and executable leak checks stop without a verdict when execution evidence is missing. Ordinary executed student errors remain distinct. No timeouts or budgets were increased.

Focused PostgreSQL acceptance: 26 passed, zero failures/errors/skips. This includes synthetic unavailable/student-error controls and the relevant real regression cases. Full-suite results at the earlier code SHA (d98bd764) remain separately recorded; focused reruns do not rewrite those results.


## Recorded validation

Full validation source: `d98bd7643b31daa1e15a0cd5324fd896524f9ca9`.

| Gate | Passed | Failed/errors | Skipped |
| --- | --- | --- | --- |
| sqlite | 395 | 0 | 7 |
| postgres | 393 | 2 | 7 |

Ruff lint, format check and configured mypy passed for that full-run source. Seven full-suite skips are the opt-in live evaluation and unavailable sibling-contract schema cases. No paid model request was used.

After the missing-verdict repair `81ac90a97467836ce60c4a04de4ffc2dd170cdd8`, 26 focused PostgreSQL cases and configured mypy passed, with zero failed/error/skipped cases. The focused selection includes the relevant real regressions and previously failing cases. It does not rewrite the older full-suite outcome.

The earlier PostgreSQL failures were an incorrect no-leak result and a missing reason code. The underlying runner result for those exact calls was not captured. Source review and synthetic faults independently reproduced the missing-verdict gap. Focused real-case reruns and explicit fault controls passed; they do not establish the cause of every earlier failure.

Existing unsigned commits in the original PR history: 2. New repair/documentation commits are signed off. The old history has not been rewritten. The repair head has not been pushed, merged, or run through hosted CI. No command to start, stop or restart the actual API/worker service was issued. Live serving state was not revalidated.
