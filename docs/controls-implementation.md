# CC-R3 implementation record

## 1. Inventory and contracts — 2026-10-08

Base: `83bd1a9`, with planning commit `a98aed3`. Fetch of origin succeeded;
`origin/main` still points to that base. Work stays in the original checkout on
`feature/shared-traffic-budget-controls`. Existing untracked `deployment/` files
are outside this change.

| Chargeable path | Current measurement / gap | Control insertion point |
| --- | --- | --- |
| `/api/sol/turn`, `/quad/v1/turn` | synchronous, no shared admission | common admission service |
| Planner, reasoner, self-evaluator | final successful response usage only | each SDK `create` call |
| Refinement, escalation, worked-example repair | repeat provider calls | same SDK boundary |
| OpenAI JSON-mode fallback and JSON repair | previous attempts lost; SDK retries implicit | disable SDK retries; authorize each explicit attempt |
| Anthropic thinking | may raise output limit above caller's limit | reserve using effective output limit |
| Injection classifier | separate provider; ordinary exceptions fail open | propagate control rejection, account at SDK boundary |
| `/api/run` grading | wall time, no usage ledger | `core.runner.run_python` |
| Retrieved-passage leak screening, draft governance, worked-example checks | indirect grading executions | same runner boundary |
| Offline analysis leak checks | also invokes pack execution | require an explicit operation context in enforced mode |

`UsageMeter` and analysis measures are research telemetry, not spending authority.
`ConsentRouter` intentionally separates research participation; operational
accounting must never depend on its persistence choice. No prompt, code, bearer
token, response text or research event belongs in the accounting tables.

### Implementation contracts

- One PostgreSQL coordinator; short serialized transactions, never held across
  external calls. SQLite supports local testing only. Independent PostgreSQL
  connections/processes must exercise races. No Redis implementation.
- Budget units: integer model tokens, integer currency microunits, runner count,
  and reserved runner wall milliseconds. Currency and price version explicit.
  Periods are fixed UTC epoch-aligned intervals. `null` means unlimited; zero
  denies spending; bypass is an explicit development mode.
- A verified scope contains deployment, institution, class and learner. Scope
  keys include ancestry. All four allowances apply atomically. Untrusted request
  IDs are never an identity source.
- An operation identifies logical work; an attempt identifies one external call.
  Reservations precede calls. Settlement is idempotent; conflicting settlement
  fails. Unknown outcomes retain liability across period rollover. Actual
  overruns remain visible and block further reservations.
- Model input is conservatively estimated from UTF-8 bytes plus framing, with an
  explicit output cap. This is an operational allowance, not an invoice guarantee:
  tokenizer, reasoning and gateway billing require deployment validation.
- Separate request-rate, queue, model and runner concurrency limits. Equal class
  rotation is the initial scheduling policy. No funded fallback after exhaustion.
- Leases fence publication; expiry does not refund external work or automatically
  retry it. Queued cancellation may release unused holds; running cancellation
  must retain uncertain liability.
- Operator inspection is a local CLI, requiring database credentials, never a
  student-facing institution summary.

### Integration prerequisites

The auth branch defines `Identity` with institution/class/learner and assignment
version scopes. The conversation branch includes deletion fences and bounded
pending turns. These were inspected as contracts, not imported as main features.
They are not merged into this branch. Thus production-owned HTTP jobs, worker
reauthorization and conversation publication remain integration gates. Enforced
mode must reject missing verified context; it must not fabricate identity from
`participant_id`. Queue APIs can be tested with trusted synthetic adapters before
those dependencies land. Existing runner containment limitations remain unchanged.

No Portage accounting guarantee is assumed; the provider boundary accounts only
for visible attempts. Gateway-internal retries need a separately validated bound.

### Step summary

Inventory complete. No application behavior changed. Next: shared ledger and
tests for parent/child races, duplicate settlement, rollover and unknown usage.

## 2. Shared ledger

Implemented separate `control_configuration` and `control_attempts` tables with
an explicit initialization entry point. Policies live in the shared database,
so workers cannot silently apply different local limits. Policy updates require
a new version; currency/period changes require a migration. Reservations retain
their price/policy snapshot. Integer accounting, four-level atomic checks,
idempotent settlement, unknown holds across rollover and recorded overruns are
covered. An overrun blocks new spending until operator investigation (no automatic
refund or automatic reset). Summary is content-free.

Validation: 8 ledger tests passed, including two spawned processes using real
PostgreSQL 16 connections against an isolated local container: one 800-token
reservation accepted, the competing reservation rejected at a 1,000-token cap.
Ruff and focused mypy passed. No live inference or production database was used.
Upstream fetch failed; origin fetch succeeded and the fork main base is unchanged.

Scalability trade-off: this first coordinator serializes mutations with one
transaction lock and computes usage from ledger rows. It is deliberately simple;
load testing and indexed/materialized balances are needed before high-volume use.

## 3. Execution accounting

OpenAI-compatible and Anthropic SDK retries are disabled. Each actual SDK attempt
now reserves independently, including format fallback, invalid-JSON repair,
thinking output and classification. Unknown response usage keeps its hold;
transport errors are not blindly retried. Telemetry records each attempt rather
than only the final parseable response. All pack execution already converges on
`run_python`; its wrapper now accounts for runs and wall milliseconds, including
grading and governance checks. CPU/memory/wall execution limits remain the existing
runner's responsibility; no stronger containment claim is made.

`CONTROLS_MODE=development_bypass` preserves local main behavior and is visible in
both health surfaces. `enforced` requires a trusted operation context and rejects
missing context before model/runner execution. Production HTTP integration is not
enabled by this flag alone. Control denial propagates through the injection guard
instead of permitting a budget failure to skip a configured safety check.

Validation: 39 targeted execution/provider/telemetry/injection tests passed.
Ruff check/format and mypy passed. Full SQLite regression: 409 collected, 401
passed and 8 skipped (including the separately passed PostgreSQL race test).
Provider responses are stubs; no real model was charged.
