# Shared-provider budget audit — 2026-10-11

## 1. Scope and actual configuration

The user reports successful manual real DeepSeek testing. This is user-provided
verification, not a new model invocation or browser test by this audit. No live
service was started/stopped, no paid request submitted, and no local budget,
identity, database, deployment ID or accepted student UI changed in this audit.

A read-only SQLite connection (`mode=ro`, `query_only`) confirmed installed
policy `local-sixhour-week-budget-20261011-v4`: USD1 per 21600 seconds, USD5 per
604800 seconds, and all four legacy scope money caps USD5.148223. The private
manifest retains amount-only cumulative USD5.148223. Snapshot at epoch
1791688664: consumed USD0.140980, outstanding-held USD0, cumulative available
USD5.007243; 14 completed / 12 failed jobs, none queued/running/unknown.
Balances can change with later user activity. No credentials or content read.

Fixed Asia/Shanghai boundaries remain 00/06/12/18 daily and Monday 00:00 weekly
(UTC epoch anchors 57600 and 316800). These local approved values are not model
defaults or formal student/course quota rules.

## 2. Implementation evidence and minimal repair

- `backend/app/controls/contracts.py`: Scope keys include deployment and nested
  institution/class/learner, never provider, model or tier. ModelQuotas applies
  both fixed buckets at deployment scope.
- `backend/app/controls/ledger.py`: reservation reads historical actual/held
  currency under the same deployment, in the same transaction as insertion.
  SQLite uses BEGIN IMMEDIATE; PostgreSQL uses a transaction advisory lock.
  Unknown liabilities carry across boundaries. Late settlement uses original
  reservation time; idempotent settlement cannot charge twice. Cumulative spend
  remains after weekly rollover. Neither restart nor a model name creates funds.
- `backend/app/agent/llm.py` and `controls/runtime.py`: both implemented SDK
  adapters cross model_call for every physical call. Planning, reasoner,
  self-evaluation, revisions and tier escalation use these adapters. OpenAI
  request-format fallback and JSON repair reserve separately. SDK automatic
  retries are disabled; timeout/missing usage preserves unknown holds. There is
  no implemented automatic cross-provider failover to claim as tested.
- Gap repaired: zero-price validation previously lived in the general launcher
  only. `config.py` now defaults billing to metered; `runtime.model_call` rejects
  invalid billing modes and zero/missing metered prices before reservation or
  provider dispatch. `controls/local_demo.py` explicitly selects unmetered for
  its synthetic zero-price provider. Token, concurrency and runner limits remain.

This is a conservative policy-price ledger, not an exact vendor invoice. One
reviewed input/output upper bound must cover every configured model, including
cache/thinking cost. Switching to a more expensive provider requires a reviewed
price-policy update; unknown pricing is not automatically free. All instances
must share the approved database, deployment ID and cumulative-cap configuration;
the local launcher pins the cap in its manifest. Arbitrary operator edits or a
new deployment identity are not equivalent to a provider/model switch.

## 3. Isolated verification

Added `backend/tests/test_shared_provider_budget.py`: actual OpenAI-compatible
and Anthropic adapter classes with simulated SDK responses verify mixed-provider
spend, model changes, short/week/cumulative denial before dispatch, actual
planner/reasoner/evaluator/revision accounting, explicit unmetered token limits,
zero-price denial, and independent spawned-process reservation/settlement.
Existing `test_model_budget_quotas.py` covers exact Shanghai boundaries, unknown
holds, pre-existing history and exact authorized local values; provider tests
cover fallback/repair, missing usage, timeouts and Anthropic cache accounting.

Final verification: full backend suite **837 passed / 0 failed / 18 skipped**
(855 collected); frontend **106 passed / 0 failed / 0 skipped**. Backend skips:
11 PostgreSQL cases without isolated database configuration, one opt-in live
behavioral evaluation, and six verifier-contract cases without the sibling
checkout. These are unverified, not passes. The new focused audit file had
7 passed / 1 PostgreSQL skip. Ruff lint and formatting passed (165 files);
mypy passed (158 source files). `git diff --check` passed.

Commands from `backend`: `python -m pytest -q`, `python -m ruff check .`,
`python -m ruff format --check .`, `python -m mypy`. From root:
`npm test --prefix frontend`. Pytest's double quiet setting hides its numeric
footer; 855 collected and 18 skip markers establish the full-suite counts.
No real model is called by these tests. Disposable test databases and fake SDKs
are used; the current local installation is not initialized or migrated.

## 4. Supported and unverified scope

| Selection | Implemented | Evidence / limit |
|---|---|---|
| openai_compatible | Yes | Simulated SDK and controlled HTTP tests; user reports real DeepSeek working. Not a promise that arbitrary APIs/models are compatible. |
| anthropic | Yes | Simulated Messages SDK and controlled HTTP tests; no live Anthropic call in this audit. |
| local_stub | Yes | Synthetic controlled flow and resource accounting; never real AI evidence. |
| bedrock | No inference implementation | Explicitly rejected by controlled launcher. |

PostgreSQL cross-process tests require an explicitly disposable
CONTROL_TEST_DATABASE_URL and remain unverified when it is absent. SQLite
process tests do not establish PostgreSQL or production load acceptance.
No production deployment or institutional entitlement/admin UI is included.

## 5. Delivery

The pending general-runtime, budget, student-error-context and documentation work
is retained for signed commits together with this audit repair. Local `.env`,
credentials, databases, private approvals, logs and generated browser previews
are excluded. Historical summaries remain records of their original runs.
The new dispatch guard takes effect after the user's next normal restart; no
prepare or policy grant is needed: repository-root `./stop-belay.ps1`, then
`./start-belay.ps1 -Check` and `./start-belay.ps1`. Eligible queued work may run
after start; unknown work is not replayed.

Feedback-context commit: `50f6841` (`fix(tutor): retain student error context and
saved request links`), signed off by Annabelle. Runtime/budget code and this
audit are delivered in the subsequent signed feature commit. GitHub HTTPS
connectivity failed during the initial remote check; push status must be reported
separately from local commit completion.
