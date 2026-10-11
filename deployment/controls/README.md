# Controlled Run / Ask — start here

Use this entry for the integrated Run code, automatic tutor feedback, Ask Sol,
optional conversation saving and recovery. The backend environment selects the
provider; the frontend is shared. Start with the explicit **local model stub**.

The combined host is local-only: loopback ports, signed synthetic test identity
and one shared R2/R3 SQLite database. It is not a production login/deployment
service. See the [full runtime guide](controlled-runtime.md) for provider fields,
pricing, migrations, retention and supported/untested boundaries.

## First use: prepare a new stub installation

Prerequisites: Python3.12 with an activated environment and the backend/core and
original teaching-pack dependencies installed. From the repository root:

```powershell
python -m pip install -r .\backend\requirements.txt -r .\backend\requirements-packs.txt
```

The following block works from **your own checkout's root**, without a fixed
developer-machine path. It refuses existing config/data directories. If already
prepared, skip this block and use the daily commands below. Do not delete old
data or overwrite an existing private config merely to rerun setup.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $belayRoot = (Get-Location).Path
    if (-not (Test-Path -LiteralPath (Join-Path $belayRoot 'backend/app/controlled_runtime.py'))) {
        throw 'Run this block from the Belay repository root.'
    }
    $configDir = Join-Path $belayRoot 'deployment/local/controlled-config'
    $dataDir = Join-Path $belayRoot 'deployment/local/controlled-runtime'
    if ((Test-Path -LiteralPath $configDir) -or (Test-Path -LiteralPath $dataDir)) {
        throw 'Config or data already exists. Retain it; use check/start or choose fresh paths.'
    }
    New-Item -ItemType Directory -Path $configDir | Out-Null
    Copy-Item -LiteralPath (Join-Path $belayRoot 'deployment/controls/controlled-runtime.env.example') -Destination (Join-Path $configDir '.env')
    Copy-Item -LiteralPath (Join-Path $belayRoot 'deployment/controls/controlled-runtime-policy.example.json') -Destination (Join-Path $configDir 'policy.json')
    Push-Location -LiteralPath (Join-Path $belayRoot 'backend')
    try {
        python -m app.controlled_runtime prepare --data-dir $dataDir --env-file (Join-Path $configDir '.env') --policy (Join-Path $configDir 'policy.json') --api-port 8004 --frontend-port 5177
        if ($LASTEXITCODE -ne 0) { throw 'Preparation failed. Do not use start to repair missing state.' }
        python -m app.controlled_runtime check --data-dir $dataDir --env-file (Join-Path $configDir '.env')
        if ($LASTEXITCODE -ne 0) { throw 'Preflight failed; inspect the private configuration.' }
    } finally { Pop-Location }
}
```

`prepare` explicitly creates this new installation's keys, test authorization,
shared database, schemas, deletion ledger and policy. It does not start services
or call a model. Private files remain ignored under `deployment/local`.

## Daily start and stop

From the repository root, with the prepared environment above:

```powershell
.\start-belay.ps1 -Check
.\start-belay.ps1
```

Start validates existing state, then runs the API, frontend and one managed worker
in the foreground. It does not prepare/migrate/reset the database or budget.
After successful startup:

- Frontend: <http://127.0.0.1:5177/dev-client.html>
- Backend: <http://127.0.0.1:8004>
- Wait for `ready:true` / `worker_alive:true` after API startup. Initial
  `checked:true` is only preflight. Private `running.json` records ownership and
  startup configuration; it is not a continuous health guarantee.
- Read-only API liveness: `Invoke-RestMethod http://127.0.0.1:8004/healthz`.

Use Run code on the original exercises: code output/checks and the labelled
`Local model stub` tutor reply are separate results. Test Ask Sol, saving off/on
and refresh recovery. Unknown outcomes must not be automatically resubmitted.
The worker may execute eligible queued jobs on start, so check the selected
provider before starting an installation with real credentials.

Stop with **Ctrl+C** in the starting terminal, or from a second PowerShell at the
repository root:

```powershell
.\stop-belay.ps1
```

Wait for foreground exit; `stop_requested` alone does not mean stopped. In-flight
work may finish. Stop does not delete data, clear task pointers or refund unknown
usage. Port conflicts must be investigated; do not stop unrelated services.

## Selecting a real provider

Use the same launcher and private env file. Implemented SDK adapters are
`openai_compatible` and `anthropic`; `bedrock` is unimplemented. Install the optional
Anthropic SDK if selecting it. Configure the provider's supported models, endpoint
where applicable, credentials and explicit capabilities as described in the
[full guide](controlled-runtime.md#supported-selection-and-capability-boundary).

For paid inference, declare `LLM_BILLING_MODE=metered` and supply reviewed positive
policy price bounds. The stub's zero-price policy is rejected in metered mode.
Changing an installed policy uses the existing policy-update procedure, not
`prepare` or a restart to replenish allowance. Stop/restart is required to load
changed environment settings. Do not commit keys, `.env`, databases or credentials.

Adapter mocks passing does not certify a hosted API/model or production load.
Previous DeepSeek browser/manual evidence applies only to that configured
endpoint. Anthropic and generic compatible endpoints have simulated-SDK evidence,
not a live-provider certification. PostgreSQL/load acceptance is separate.

## Which file does what?

| File | Purpose |
|---|---|
| [`start-belay.ps1`](../../start-belay.ps1) / [`stop-belay.ps1`](../../stop-belay.ps1) | Checkout-relative daily wrappers; `-Check` does not start services |
| [`backend/app/controlled_runtime.py`](../../backend/app/controlled_runtime.py) | General Python entry: `prepare`, `migrate`, `check`, `start`, `stop`; assembles the existing APIs, identity, worker and cleanup |
| [`start-controlled-runtime.ps1`](start-controlled-runtime.ps1) | Foreground PowerShell launcher; delegates to `python -m app.controlled_runtime start` |
| [`stop-controlled-runtime.ps1`](stop-controlled-runtime.ps1) | Cooperative stop for the matching installation; never kills by port/PID |
| [`controlled-runtime.env.example`](controlled-runtime.env.example) | Public config template; defaults to `local_stub`, no real model calls |
| [`controlled-runtime-policy.example.json`](controlled-runtime-policy.example.json) | Synthetic zero-price policy with finite resource limits; not a paid-provider pricing profile |
| [`controlled-runtime.md`](controlled-runtime.md) | Detailed operator guide |
| [`controlled-runtime-summary.md`](controlled-runtime-summary.md) | Implementation steps, verification evidence and remaining limits |

Ignored `deployment/local/run-feedback-verification/deepseek_preview.py` and its
dedicated scripts are historical local previews, not the general team entry.


## Existing credential file (no repeat key entry)

From the repository root, the daily wrapper defaults to
`deployment/local/controlled-config/.env`, the prepared DataDir
`deployment/local/controlled-runtime`, and supplemental `backend/.env` if present.
Only OPENAI_API_KEY, LLM_API_KEY and
ANTHROPIC_API_KEY are read from the supplemental file; other settings there
cannot change runtime configuration. Nonempty inherited credentials win, then
nonempty credentials in EnvFile, then CredentialsEnvFile. Within the OpenAI
adapter OPENAI_API_KEY takes priority over LLM_API_KEY. API and its managed
worker share this loaded process environment. No key is copied to another file.

```powershell
.\start-belay.ps1
```

Default paths are relative to the checkout; explicit paths are relative to the
calling directory or absolute. To choose another **already prepared** profile:

```powershell
.\start-belay.ps1 -Check -DataDir .\deployment\local\other-runtime -EnvFile .\deployment\local\other-config\.env -CredentialsEnvFile .\backend\.env
.\start-belay.ps1 -DataDir .\deployment\local\other-runtime -EnvFile .\deployment\local\other-config\.env -CredentialsEnvFile .\backend\.env
.\stop-belay.ps1 -DataDir .\deployment\local\other-runtime
```

Pass `-CredentialsEnvFile ''` to deliberately omit the supplemental file. Explicit
runtime EnvFile settings override inherited non-secret configuration; omitted
fields inherit the process/defaults, so use a complete profile. Supplemental
backend/.env contributes only the three allowlisted credential fields. The
installation manifest owns DB/auth paths, deployment ID and persisted deadline.
Configured credential presence does not prove the key is valid at the vendor.
The foreground launcher prompts securely only if the selected provider has no
configured key. Check does not prompt or call a model:

```powershell
.\start-belay.ps1 -Check
```

Stop only this installation cooperatively from repository root:

```powershell
.\stop-belay.ps1
```

Start never prepares/rebuilds the database or renews the persisted authorization.
An expired window remains expired. Restart may execute eligible queued work;
it does not replay unknown requests. Review pending work before starting.


Keep the foreground window open. The actual runtime page is
`http://127.0.0.1:5177/dev-client.html` (when configured for5177/8004).
`tests/fixtures/generated-feedback-preview.html` is a fixed-response offline
UI test fixture, **not** a real provider preview or evidence of live feedback.
The fixture is never linked as the product entry.

## Reading check output and startup failures

Check prints provider/models, policy/price version, authorization window,
`jobs_by_state`, `queued_work_may_execute`, `start_allowed` and `blockers`.
`inference_window_expired` returns a nonzero exit without changing the window.
This snapshot neither reserves funds nor proves that every future request fits
all budgets. Check does not bind ports or validate a key through the provider.
Review queued counts before start: a real-provider worker may spend on eligible
queued tasks immediately. Unknown outcomes remain under the existing recovery
protocol and are never automatically replayed. Do not erase queues or pointers.

First start of an already approved, unarmed fixed window persists its start/end
once. This activates existing authorization; it does not create a new grant.
The duration is a local test-policy decision, not a provider requirement, bearer
token lifetime, per-student quota or saved-conversation retention period. The
two-hour validation choice is not a universal requirement for models or courses.
The bounded mode retains its 7200-second maximum; local development can instead
explicitly select a cumulative amount-only budget with **no inference deadline**.

From the repository root, after stopping the matching installation:

```powershell
.\start-belay.ps1 -UseAmountOnlyBudget
.\start-belay.ps1 -Check
.\start-belay.ps1
```

The first command is a one-time configuration operation, not a service launch.
It archives the previous fixed window and stores `amount_only_budget` in the
private `runtime.json`, pinning the previous cumulative cap. It never updates the
database, price policy, deployment ID, usage or unknown holds. Repeating it is
idempotent. It refuses active/queued/cancel-requested work, a running host or a
pending new grant; inspect these rather than clearing or replaying them. `check`
then reports `inference_window: {state: "disabled", mode: "amount_only"}`.

For a genuinely new installation, use `CONTROLS_INFERENCE_WINDOW_SECONDS=0`,
`CONTROLS_INFERENCE_EXPIRES_AT=0` and a finite approved
`CONTROLS_INFERENCE_TOTAL_MICROUNITS` in its private runtime env before prepare;
then explicitly persist amount-only mode with the command above. No amount is
supplied to the conversion command: an existing timed installation must have its
own persisted ceiling. Missing ceilings fail closed. One USD = 1,000,000 microunits.

Persisted amount-only mode overrides old window settings and replacement caps in
the env file, for both API and worker. It does not disable model-call timeouts,
job deadlines, identity expiry, class isolation or conversation/result retention.
All per-scope limits still apply. The cumulative cap counts earlier accounting
periods too; this does **not** add a daily monetary allowance. Exhaustion still
requires separately authorized money, never a restart or automatic renewal.

Do not delete/edit the manifest to switch modes. Existing timed profiles and
their explicit additional-money workflow are retained. Switching an amount-only
profile back to a new bounded authorization is not exposed by this command; it
requires a separate reviewed transition. This change adds no administrator page
or grant scheduling system. Details and verification: [implementation summary](amount-only-budget-summary.md).

### Local developer budgets and formal teaching quotas

The local `amount_only` profile is a finite developer testing allowance, not a
formal learner quota. A larger local budget must be explicitly authorized;
review token/run/wall-time caps as well so a money increase does not leave another
tiny test limit in place. Preserve old spend and unknown holds. `update-policy`
alone does not change the manifest's cumulative ceiling, and `authorize-window`
is a timed grant operation, not an amount-only top-up.

The [audit, pending local recommendation and Greg discussion requirements](local-and-course-budget-plan.md)
keep those concerns separate. Its proposed numbers are **not applied defaults**.
Formal teaching may refresh learner allowances daily or every configurable few
hours while course access is valid, without resetting the class/course cumulative
budget or ledger history. That independent policy/interface remains unimplemented
and requires agreement with Greg; this round adds no administrator page or quota
refresh mechanism.

The newer [local short-period + weekly plan](local-period-budget-plan.md) adds
optional deployment-wide model quotas, default disabled, using the same ledger
transaction. It does not implement formal learner quota renewal. Both fixed
windows, cumulative funding and existing scoped limits must pass. UTC anchors
define refresh boundaries; old consumption and unknown holds remain counted.
The original proposals did not authorize spending. The subsequent explicit
2026-10-11 local authorization **has been applied**: add USD5, retain the prior
balance and pin a USD5.148223 cumulative ceiling, with USD1/six hours and USD5/week.
Timezone **Asia/Shanghai (UTC+08:00)** uses fixed 00/06/12/18 boundaries and Monday
00:00 weeks. Short refresh does not reset week consumption; weekly refresh does
not reset cumulative consumption or grant money. No expiry is restored and no
non-money resource limit was raised. These are private local test settings, not
formal student/course defaults. See the [applied summary](local-budget-authorization-20261011-summary.md).

Once an exact incremental grant and its policy are approved, the prepared entry
is `./start-belay.ps1 -BudgetAuthorization <approved-json> -BudgetPolicy <policy-json>`.
It updates a stopped installation without starting services; normal `-Check`,
start and stop stay unchanged. It preserves the amount-only mode and prior
balance, and rejects changed price/period/traffic configuration. See the plan
for the concrete repository-relative paths, recovery contract and test evidence.
Start uses an exclusive installation lock. Stop requires a matching nonce and a
held lock; it signals the host cooperatively and never kills a PID/port. Worker
cleanup continues to enforce temporary-content and saved-history retention.

| Symptom | Action |
|---|---|
| Missing EnvFile | Keep the `.env` filename: `controlled-config/.env`, not `controlled-config.env`. Use the repository root or explicit paths. |
| `required_file_missing` / schema error | Inspect DataDir. Prepare only genuinely new paths; preserve existing files and use explicit migration for schema upgrades. |
| `runtime_already_running_or_locked` | Inspect the existing foreground terminal/receipt. Do not delete a live lock or launch another worker. |
| `port_in_use` | Identify the owner; stop only a confirmed Belay installation via its DataDir, or deliberately choose other ports at preparation. |
| `inference_window_expired` | Request explicit budget/window review. Restart, env edits or prepare must not be used to renew it. |
| `pending_authorization_has_active_work` | Inspect queued/running/cancel-requested tasks before activating a newly approved window; no automatic queue clearing. |
| `active_work_requires_review` / `pending_authorization_requires_review` | Budget-mode conversion refuses existing active work or a pending grant. Inspect its state; do not clear records to bypass the guard. |
| `finite_persisted_budget_required` | The mode transition requires a finite cumulative cap; an existing fixed window must carry its own ceiling. Do not silently infer or increase it. |
| Usage limit during a task | Inspect the specific policy and held usage; this does not prove provider account balance is empty. |
| `runtime_not_running` / receipt mismatch | No matching locked host was verified. Inspect stale receipts manually; no process was killed. |
| `controlled_runtime_unavailable` | Fail-closed configuration/schema/policy check; inspect private configuration and dependencies without exposing secrets. |

Use separate PowerShell lines for `Set-Location` and the script invocation.
No execution-policy bypass is provided. A script error does not authorize resetting
the installation. Additive schema migration is explicit: stop, preserve the DB
and deletion ledger, then follow [migration instructions](controlled-runtime.md#migration-policy-and-real-providers)
using the already installed policy. Start never performs that migration.

## Model configuration examples and supported scope

| Provider | Implemented | Validation boundary |
|---|---|---|
| `openai_compatible` | Configurable Chat Completions SDK | Mock SDK and controlled saved/unsaved scenarios; previous live DeepSeek evidence covers that configuration only |
| `anthropic` | Messages SDK, its own thinking/cache usage | Mock SDK and controlled saved/unsaved scenarios; live Anthropic unverified |
| `local_stub` | Deterministic controlled test provider | Isolated flow tests, no remote inference |
| `bedrock` | Inference unimplemented | Rejected before execution |

DeepSeek is an environment-selected compatible endpoint, not a dedicated launcher.
No arbitrary vendor API compatibility is promised. For an approved compatible
endpoint, edit the private runtime EnvFile (illustrative placeholders only):

```dotenv
PROVIDER=openai_compatible
OPENAI_BASE_URL=https://your-approved-endpoint.example/v1
MODEL_FAST=operator-selected-fast-model
MODEL_STRONG=operator-selected-strong-model
OPENAI_RESPONSE_FORMAT=json_object
OPENAI_THINKING_MODE=
OPENAI_REASONING=0
OPENAI_FINAL_CONTENT_ONLY=1
LLM_TIMEOUT_SECONDS=30
LLM_BILLING_MODE=metered
```

For Anthropic use `PROVIDER=anthropic`, `ANTHROPIC_MODEL_FAST`,
`ANTHROPIC_MODEL_STRONG`, `ANTHROPIC_THINKING`, `ANTHROPIC_THINKING_BUDGET` and
`ANTHROPIC_API_KEY`; install its optional SDK. OpenAI capability settings do not
alter Anthropic requests. Leave optional fields off unless the selected endpoint
supports them. Store keys only locally; never paste real keys into these examples.

Changing the key alone is insufficient. Stop first; review both model tiers,
capabilities, positive conservative input/output prices, finite limits and held
usage. Apply necessary price/policy changes through `app.controls.cli update-policy`
against the same coordinator with a new policy/price version. Do not use prepare
or migrate to reset spend. `COST_PER_1K_*` is telemetry only; control-policy prices
govern reservations/settlement and must cover thinking/cache and both tiers.
Missing usage keeps the reservation; invoice-specific discounts are not implemented.
Then check and restart to load the reviewed environment. No renewal is implicit.

See [daily-entry implementation evidence](daily-entry-summary.md). Lifecycle mock
tests are not live-listener, production deployment or load acceptance.
