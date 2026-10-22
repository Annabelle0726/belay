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
