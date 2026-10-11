# Local testing window: time-only extension proposal

**Superseded:** the subsequent request selected optional deadlines / amount-only
local development. See [the implementation summary](amount-only-budget-summary.md).
The proposal below is retained as history, not a currently available renewal.

Status: design/documentation only, awaiting the operator's duration approval.
No runtime code, actual policy, private env, manifest, key or database was changed.

## Audit — 2026-10-11, Asia/Shanghai

The private runtime EnvFile selects CONTROLS_INFERENCE_WINDOW_SECONDS=7200.
The effective installation window is persisted in runtime.json:
2026-10-10 20:31:16 through 22:31:16 Asia/Shanghai. It has expired.
environment() loads that persisted end/cumulative cap over env overrides.
arm_inference_window() writes first-start timestamps once; model_call checks the
deadline before dispatch and keeps normal settlement/unknown-hold behavior for
already-sent requests. Restart or editing the env cannot renew the window.

Current read-only ledger snapshot (USD; one microunit = USD0.000001):

| Quantity | Value |
|---|---:|
| Cumulative cap | 0.148223 |
| Settled consumption, across periods | 0.114475 |
| Unresolved reservations | 0.000000 |
| Cap less consumption and reservations | 0.033748 |

The remaining amount is not newly granted money and is not currently spendable
through the expired window. These are ledger values, not a vendor-account balance
or invoice. Re-read them before any approved update. Keep the common SQLite DB,
deployment ID and policy controlled-validation-run-cap-20261010-v3 unchanged.
Its 86400-second accounting period is distinct from the test authorization window;
the cumulative cap remains effective across period boundaries.

Implementation evidence:
- backend/app/controlled_runtime.py: environment, validate_window,
  arm_inference_window and validate_policy (current 7200-second checks).
- backend/app/controlled_runtime.py: authorize_window (positive additional-money
  authorization, expired previous window, forfeiture, installation lock,
  expected consumption/policy, idempotent ID, atomic manifest replacement).
- backend/app/controls/runtime.py: check_inference_deadline and controlled dispatch.
- backend/app/controls/ledger.py: cumulative consumed/reserved accounting.

The local signed bearer currently lasts 300 seconds. R2 saved-conversation
retention is separately configured. Neither determines the test window, and
neither would change in this proposal. Per-learner/class/institution budgets also
remain independent. Two hours is not a paid-provider or formal-course requirement.

## Recommended duration and impact

Recommend one explicitly approved **24-hour wall-clock window**, activated at the
first manual start after the update. Example: start on 2026-10-11 at 10:00
Asia/Shanghai; end on 2026-10-12 at 10:00. This is an illustration pending approval,
not an already scheduled grant. Persist the actual start/end at activation.
Offline/stopped time still counts; a restart does not extend the end. A shorter
8-hour alternative would end at 18:00 for the same illustrated start.

Benefit: sustained daytime/overnight debugging without a two-hour interruption.
Tradeoff: paid inference remains eligible for longer, but only within the same
cumulative cap and all existing per-scope limits. Money may run out well before
24 hours. Student error handling, model selection, credential lifetime, research
consent, retention, pricing, token/run limits and accounting periods do not change.
Time expiry and insufficient budget remain independent reasons to reject work.

## Required minimal implementation after approval

There is currently **no supported safe command** for the requested zero-money
24-hour extension. Changing only the env fails the 7200-second validation and
cannot override the persisted deadline. Existing authorize-window requires
additional_microunits > 0, recalculates cap as consumption + additional amount and
uses unused_balance=forfeit. Passing zero or relabeling the balance is incorrect.

Extend the existing controlled_runtime command dispatcher with a distinct
time-only operation; reuse installation loading, locking, window activation and
atomic manifest-write helpers. Do not create a new runtime or billing mechanism.
Replace repeated 7200 literals with a documented local test-duration bound that
supports the approved duration. This bound is an implementation safeguard, not
the effective duration or an automatic grant. Keep explicit finite time approval.

The operation must:
1. Require a stopped matching installation and an explicit approval record:
   unique authorization ID, duration, expected previous-window identity/hash,
   expected cumulative cap, policy version and deployment. For this request it
   adds exactly zero microunits and preserves, rather than forfeits, unused balance.
2. Re-read queued/running/cancel-requested tasks and require investigation before
   activation. Keep unknown tasks and reservations; do not replay, release or
   clear them. Recheck immediately before the first manual start as well.
3. Preserve the cumulative cap bit-for-bit (currently 148223 microunits), all
   policy fields, existing consumed amounts, reservations and common DB. Do not
   call Ledger.update_policy for a change that does not change policy money/prices.
4. Archive the previous authorization and record the time-only amendment without
   rewriting historical records. Publish a pending duration with the SAME cap,
   then arm once on first manual start. Existing expired authorization fences
   dispatch until successful publication/activation. A same-ID/same-proof retry
   is idempotent; conflicting reuse fails. Replaying an old update cannot renew it.
5. Use atomic manifest replacement under the installation lock; no database
   transaction is needed to change the ledger because there is no ledger write.
   Re-read consumption/holds for reporting; later authoritative settlements must
   still count under the unchanged cap. Do not claim atomicity with external work.
6. Continue enforcing the existing amount cap, unknown holds and fixed deadline
   before every model dispatch. No automatic renewal, startup reset or paid probe.

Proposed shortest operator workflow (interface NOT implemented yet): prepare the
reviewed local amendment file after confirmation, expose it through
`start-belay.ps1 -ExtendWindow <approval-file>`, then use the ordinary `-Check`
and manual start. The extension operation must exit without starting listeners
or inference. Daily start/stop commands remain unchanged. A time-only extension
must never be silently bundled into ordinary start.

## Validation required before applying to the real installation

Use isolated DBs, synthetic approvals and mocked clocks/providers to prove:
24-hour first-start activation; restart stability; expiry denial; same cumulative
cap across UTC/accounting boundaries; previous spend and unknown holds retained;
no DB/key/deployment/policy mutation; queued/active work rejection; idempotent
retry and conflicting ID rejection; crash before/after atomic manifest replace;
no automatic new task or paid model call. Only after duration confirmation and
these checks should the actual private authorization be updated.

## This step's summary

Changed documentation only: root README.md, deployment/controls/README.md,
controlled-runtime.md, public controlled-runtime.env.example comments and this
design. Historical implementation summaries retain the original two-hour record.
Read-only code/config/ledger audit completed. No runtime tests run for prose-only
changes. Time-only extension code, isolated tests, concrete update command and
actual authorization update remain pending approval/implementation. No commit,
push, deployment, prepare, ledger reset or paid model request.
