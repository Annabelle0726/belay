# Local controlled-runtime budget policy

Use the [launch README](README.md) for setup and daily commands; see the
[shared-provider audit](shared-provider-budget-audit-summary.md) for evidence.

## Finite cumulative funding and optional time limits

`amount_only` has no inference authorization deadline, but retains an approved
finite cumulative ceiling. It never renews funds. Timed profiles remain supported
with a persisted first-start deadline (currently up to 7200 seconds); restart
does not move that deadline. This is a configurable local test policy, not a
model requirement, login lifetime or student entitlement.

The operator selects the cumulative ceiling and each scope limit for the
installation. Models and providers share the deployment ledger. Keep the
deployment identity and its database when changing models.

## Fixed boundaries

The optional `model_quotas` policy requires both limits and both anchors.
`short_period_seconds` sets the short window (whole hours from 1 through 24).
`short_anchor_utc` and `week_anchor_utc` are Unix timestamps in seconds. Choose
each anchor at an intended boundary. The ledger repeats the short window at its
configured interval and the weekly window every seven days, using elapsed UTC
seconds. Each interval includes its start and excludes its end. Changing the
host timezone or restarting the worker does not move either boundary.

An operator who wants Monday midnight in a particular location must translate
that boundary to UTC when preparing the policy. Fixed intervals do not follow
daylight-saving changes. Omit `model_quotas` to use only the other configured
limits.

Short-period renewal does not reset weekly consumption. Weekly renewal does not
reset cumulative consumption or add funds. Settlements belong to the original
reservation timestamp. Unknown reservations encumber both new buckets until
reconciled. Previously recorded usage counts when quotas are enabled. Legacy
scope periods are independent; their existing UTC alignment is unchanged.

## Explicit changes only

From the repository root, normal use is:

```powershell
.\start-belay.ps1 -Check
.\start-belay.ps1
# In a second terminal, when stopping is intended:
.\stop-belay.ps1
```

For an explicitly approved increment, prepare private authorization and policy
JSON files and use the existing operator command on a stopped installation:

```powershell
.\start-belay.ps1 -BudgetAuthorization <approved-json> -BudgetPolicy <policy-json>
```

`authorize-budget` requires the unique authorization ID, expected old ceiling,
deployment and policy version, explicit increment and retained-old-balance
decision. Identical retries do not add money twice; conflicting changes reject.
It checks ownership/lock and active work. It neither starts workers nor replays
unknown tasks. Price, legacy period and traffic changes are rejected by this
operation; model/price changes use a separately reviewed `update-policy`.

Policy update and atomic manifest replacement are not one cross-file transaction.
If manifest replacement fails, the old smaller cumulative ceiling stays in
force. Retry the same approved files to finish that grant, not a new increment.
Do not edit the manifest, prepare again or clear the ledger to bypass a denial.

An existing timed installation can explicitly retain its finite ceiling and
remove only the deadline with `./start-belay.ps1 -UseAmountOnlyBudget`. This
refuses pending grants and active/queued work; no budget increase is implied.
All settings apply to the API and worker. Identity expiry, job/model timeouts,
conversation retention and token/resource limits remain independent.

## Formal teaching remains separate

Configurable student daily/hourly entitlement renewal during valid course access,
with spending accumulated against course/class funding, is a candidate for
institutional review. Responsibilities, semester rules and administrator UI are
not implemented by these local developer policies.
