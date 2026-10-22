# PR #14 / issue #21: trusted shared Ask runtime

## What changed

The optional injection classifier now uses only its separately configured sovereign endpoint and model. It cannot fall back to the general tutoring provider. Each physical send, including a supported-format fallback, passes through the existing shared reservation/accounting runtime. SDK retries are disabled. Malformed boolean/confidence fields remain explicit malformed evidence, and diagnostics contain bounded categories rather than raw exception text. Budget or authorization denials propagate instead of being treated as an optional classifier outage. The deterministic output governance remains required.

The assignment mode/stance contract from PR #13 is integrated into the R3 adapters without merging branches. Legacy string grants authorize study/peer only; oracle/control and teach require explicit trusted pairs. Queue bindings now carry the exact version, generation, policy revision, allowed pairs and selected behavior. Admission, execution, further model calls, staging, publication, polling and referenced-result retrieval recheck the original principal and permission snapshot. A different subject with the same learner scope cannot take over work.

Saved turns retain an internal authorization receipt in the existing JSON response, within the existing dialogue/control transaction. History, replay, model context and reply references validate the receipt. It is not returned to students and its bytes count toward retention limits. Pre-upgrade job bindings and saved assistant turns without reliable permission metadata fail closed; no ownership or behavior is inferred and no SQL schema migration is introduced.

Existing inference unknown liabilities, settled usage, deployment identity, funding limits, queue protection and code-execution accounting are retained. A revocation does not refund already dispatched work. No running local service, actual budget or operating database is updated by these repairs.

## Validation

Tests use synthetic signed grants, temporary databases and model SDK stubs. They cover both HTTP surfaces, queued/running/completed permission changes, legacy denial, old binding rejection, history/reference boundaries, classifier per-attempt accounting, unknown usage and budget denials. Full SQLite/PostgreSQL/frontend and quality results are recorded in the repair summary. CI already supplies the controls and dialogue PostgreSQL opt-in URLs and runs frontend tests; dedicated acceptance must fail if PostgreSQL coverage is skipped.

## Scope and remaining integration

The operator file is a local authorization adapter, not a completed Cairn authorization transport. Re-grants require a new generation and changed policy requires an advanced revision; restoring identical old files cannot represent an unobserved revoke/regrant. Durable ordered/expiring updates, restart-safe high-water tracking and platform identity migration are still contract work in #22.

Local token/cost amounts are operational estimates under configured conservative rates, not authoritative Portage receipts or a provider invoice. Verified Portage dispatch/receipt idempotency and reconciliation are not implemented by this patch. Keep Belay's shared ledger and workload protections until that handoff is demonstrated. This PR adds no administration dashboard or model roster and does not claim a verified end-to-end platform connection.

All repair commits have DCO sign-off. Existing unsigned history is preserved for contributor/maintainer resolution; no force push, push or merge was performed.


## Additional missing-verdict protection

A resource-constrained validation run exposed an existing failure path: a runner with no grading verdict could be treated as a checked non-solution. The grader now records verification availability, and executable leak checks stop without a verdict when execution evidence is missing. Ordinary executed student errors remain distinct. No timeouts or budgets were increased.

Focused PostgreSQL acceptance: 3 passed, zero failures/errors/skips. This includes synthetic unavailable/student-error controls and the relevant real regression cases. Full-suite results at the earlier code SHA (4f41538a) remain separately recorded; focused reruns do not rewrite those results.


## Launcher regression fixtures

The first complete SQLite run at `76e9e2b` reported 989 passed, 3 failed and 18 skipped. Two synthetic launcher cases granted only study/control but then submitted study/peer jobs; the new server correctly denied those requests. The fixtures now explicitly authorize both tested pairs. Ordinary legacy grants remain study/peer only.

The third failure was Windows PowerShell emitting localized stderr bytes that a UTF-8 subprocess reader could not decode. The wrapper test now tolerates replacement of undecodable diagnostic characters while retaining its assertions about the missing configuration and no preparation/start side effects. All five launcher/wrapper cases passed after these test-only corrections. The superseded full result is preserved separately; the subsequent complete run and final targeted evidence are recorded separately in the repair summary.

The separate PR branches have not been merged or validated as one combined deployment. In particular, integrating PR #7's replacement runner with R3 must preserve both the container boundary and the shared `runner_call` accounting hook. Class-sized throughput, a fresh sandbox image build and gVisor are not demonstrated by these repairs.


## Assignment access and tutoring permissions

Run code and a missing-request recovery fence require current assignment access, not a default study/peer tutoring grant. Each captures a purpose-bound original authorization snapshot; a fence cannot load, stage or publish an Ask. Actual tutoring still requires the selected trusted mode/stance pair before admission and at subsequent boundaries. Removing the original principal or changing its grant blocks code-result delivery in both enforced and development-bypass modes. An accessible assignment may permit code execution while allowing no tutoring pair.

The later full SQLite run at e4af0a7 had 991 passed, one failed and 18 skipped: its launcher readiness loop did not catch a socket TimeoutError. The test now retries that error within the existing 20-second startup deadline; all four launcher variants inject an initial probe timeout to exercise this path. No application timeout was increased. HTTP error-wiring tests also use an explicit in-memory consent router, avoiding dependence on a globally imported SQLite connection. Earlier failures remain recorded, and focused results are not described as a clean final full suite.
