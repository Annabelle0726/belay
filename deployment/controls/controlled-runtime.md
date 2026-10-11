# Belay controlled runtime

New team members: begin with the [setup and launch README](README.md), which
includes portable repository-root PowerShell commands and an entry-file map.

This tracked entry uses the existing R1 authentication, R2 optional conversation
saving, R3 admission/accounting/AskAdapter, and the existing Run/Ask UI. Provider
selection belongs to the backend environment. No model, endpoint, thinking mode,
vendor price or paid validation window is embedded in the launcher.

The included combined host is **loopback-only, signed synthetic local identity,
one shared SQLite database**. It is a reusable local integration entry, not a
production credential issuer. Production uses operator-provisioned R1 identity,
the same `app.main:app` and `app.controls.jobs_worker` with a shared PostgreSQL
database; this change does not implement institutional SSO or production rollout.

## Supported selection and capability boundary

| PROVIDER | Adapter / authentication | Tested here | Limits |
|---|---|---|---|
| local_stub | Existing local DemoProvider; no SDK/network | Signed saved/unsaved HTTP + actual runner + controlled worker, config/lifecycle and offline UI tests | Synthetic feedback only |
| openai_compatible | OpenAI Chat Completions SDK; OPENAI_BASE_URL / OPENAI_API_KEY, MODEL_FAST / MODEL_STRONG | SDK-shaped responses through real adapter and signed controlled HTTP | Requires supported request, JSON text and usage fields; not arbitrary API compatibility |
| anthropic | Anthropic Messages SDK; ANTHROPIC_API_KEY, ANTHROPIC_MODEL_FAST / STRONG | SDK-shaped responses through real adapter and signed controlled HTTP | Optional `anthropic` package required; text blocks, not reasoning blocks, are released |
| bedrock | Existing documented stub | Rejected before preparation/start | No implemented inference; not supported for execution |

Both live adapters use `LLM_TIMEOUT_SECONDS` (default30), SDK `max_retries=0`, and
the existing controlled `model_call`. OpenAI-compatible initial JSON-mode format
rejection400/422 can make one fallback attempt; invalid JSON can make one repair
attempt. Each is separately metered. A lost response/timeout never causes an SDK
or blind inference retry. Anthropic currently fails invalid JSON without repair.

OpenAI-compatible capabilities are explicit, not inferred from endpoint/model:

- `OPENAI_RESPONSE_FORMAT=json_object|none` (default json_object).
- `OPENAI_REASONING=1` and `REASONING_STRONG` retain the existing effort behavior.
- `OPENAI_THINKING_MODE=` sends nothing; `enabled|disabled` sends the endpoint's
  `extra_body.thinking.type` on all physical attempts. Only enable for an endpoint
  documented to support it. This does not change Anthropic requests.
- `OPENAI_FINAL_CONTENT_ONLY=1` (default) never treats reasoning_content as the
  released answer. Explicit legacy fallback0 remains available if required by a
  reviewed compatible endpoint.
- `ANTHROPIC_THINKING` and `ANTHROPIC_THINKING_BUDGET` retain that adapter's own
  capability; its effective output bound includes thinking tokens.

OpenAI prompt/completion usage totals include cache/reasoning when reported in
those totals. Anthropic input includes separately reported cache creation/read
tokens. Missing or unusable usage keeps the conservative reservation, even when
a valid answer can be delivered. Vendor-specific discount/invoice accounting is
not implemented. No new adapter for an arbitrary API is implied.

## Prepare and run a synthetic installation

Run these manually from the repository. Paths and ports are distinct from the
existing DeepSeek8003/5176 environment; nothing stops or changes that service.
The `.env`, keys, DB, authorization and receipt remain ignored local files.
These setup-copy commands are for first use with fresh paths. If the config
directory already exists, retain its files and use `check/start`; do not overwrite
an operator's existing `.env` or policy with examples.

```powershell
Set-Location C:\Projects\EduCloud-Ecosystem\belay
New-Item -ItemType Directory -Path .\deployment\local\controlled-config -ErrorAction Stop | Out-Null
Copy-Item .\deployment\controls\controlled-runtime.env.example .\deployment\local\controlled-config\.env
Copy-Item .\deployment\controls\controlled-runtime-policy.example.json .\deployment\local\controlled-config\policy.json
Set-Location .\backend
python -m app.controlled_runtime prepare --data-dir ..\deployment\local\controlled-runtime --env-file ..\deployment\local\controlled-config\.env --policy ..\deployment\local\controlled-config\policy.json --api-port 8004 --frontend-port 5177
python -m app.controlled_runtime check --data-dir ..\deployment\local\controlled-runtime --env-file ..\deployment\local\controlled-config\.env
```

`prepare` only accepts a **new** data directory. It creates the signed local
identity, stable installation-specific issuer, encrypted execution key, original
active teaching pack grants, deletion ledger, R2/R3/store schemas and operator
policy. No inference probe/listener/worker starts. It never adopts a legacy DB,
imports student data, changes course terms or initializes the old previews.
Check the printed provider and paths before starting. Explicit env-file settings
override inherited configuration (so an inherited PROVIDER cannot silently turn
the stub profile into paid inference). Process API credentials take priority over
file credentials. Without an env file, process configuration is used. Assembly-owned
DB/auth paths always come from the installation. No secrets are echoed by the entry.

Start (foreground, no background process helper):

```powershell
& 'C:\Projects\EduCloud-Ecosystem\belay\deployment\controls\start-controlled-runtime.ps1' -DataDir 'C:\Projects\EduCloud-Ecosystem\belay\deployment\local\controlled-runtime' -EnvFile 'C:\Projects\EduCloud-Ecosystem\belay\deployment\local\controlled-config\.env'
```

After successful start, open `http://127.0.0.1:5177/dev-client.html`; backend is
`http://127.0.0.1:8004`. `running.json` records the selected provider/models,
policy version and worker receipt. It is not a provider invoice or perpetual
health assertion. Start checks existing schemas/fences/keys/policy and disables
legacy SqlStore automatic DDL. It does not prepare, migrate, rotate identity,
reset grants or replenish budget. Eligible queued jobs can execute after start;
unknown jobs are never automatically replayed. The backend/worker use the same
settings and DB. Reconfiguration requires stopping and restarting this entry.

Run code displays execution output/checks and then automatically submits feedback
through the existing client. Ask submits manually. With saving off, encrypted
temporary recovery input/results expire under R3. Saving remains opt-in on the
page, independently of research consent. Saved history keeps the configured R2
creation-based retention/deletion/revision contracts. Refresh queries the original
task ID; unknown outcomes require inspection, never automatic re-submission.
The accepted animation and sanitized Markdown paths are unchanged.

Stop with Ctrl+C in the starting terminal, or from another terminal:

```powershell
& 'C:\Projects\EduCloud-Ecosystem\belay\deployment\controls\stop-controlled-runtime.ps1' -DataDir 'C:\Projects\EduCloud-Ecosystem\belay\deployment\local\controlled-runtime'
```

Stop is cooperative, not a cancellation feature: it stops new claims, allows
in-flight bounded work to return, and shuts down the matching worker/API/frontend.
It never kills unrelated processes by port/PID. `stop_requested` does not mean
already stopped; wait for the original foreground command to return and its
running receipt to disappear. A hard crash leaves holds/leases for the existing
unknown/reconciliation protocol. No refund is inferred from process exit.
Cleanup runs with the worker: temporary control content each loop and expired/
deleted R2 conversations every30 seconds, including when new saving is disabled.
Fatal worker exit stops API admission; resource-control denials remain conservative.

## Migration, policy and real providers

For a prepared installation requiring additive schema upgrade, stop it, back up
the DB **and independent deletion ledger** according to R2 policy, then explicitly:

```powershell
Set-Location C:\Projects\EduCloud-Ecosystem\belay\backend
python -m app.controlled_runtime migrate --data-dir ..\deployment\local\controlled-runtime --env-file ..\deployment\local\controlled-config\.env --policy ..\deployment\local\controlled-config\policy.json
```

Migration does not replace missing identity/encryption/deletion fences or silently
change installed policy. `prepare` is not a recovery command. For a reviewed
policy change, use the existing `app.controls.cli update-policy` with the exact
installation's `CONTROLS_DATABASE_URL`, a new policy version and unchanged
currency/period. Never use initialization to reset spent allowance.

The included policy declares **unmetered synthetic zero prices**, finite limits
and USD0.10 per coordinator period. That is not the prior one-hour paid validation
profile, vendor pricing, or authorization to enable a paid model. Metered startup
rejects zero/missing prices; `LLM_BILLING_MODE=metered` requires positive reviewed
input/output per-token currency microunit bounds covering both tiers, thinking,
cache and repair attempts. Self-hosted/free inference requires an explicit
`unmetered` declaration; it still has token/rate/runner/concurrency limits.
Budget periods reset under the existing policy; unknown holds carry forward.
There is no independent per-task dollar cap. Do not equate ledger cost to invoice.
`COST_PER_1K_PROMPT` / COMPLETION are telemetry-only estimates, not control policy.

For an explicitly approved one-time local validation, set
`CONTROLS_INFERENCE_WINDOW_SECONDS` (currently validated as 1–7200) and
`CONTROLS_INFERENCE_TOTAL_MICROUNITS` to the approved total. First manual `start`
persists the deadline and total in the installation manifest before dispatch;
`check` never arms it. Restarts reuse it, even if environment values are removed
or changed. Expired authorization rejects restart and every new external model
attempt. Already-sent responses still settle normally; a lost response retains
its hold. The cumulative cap counts settled costs plus unresolved reservations
across all coordinator periods in the same deployment, inside the reservation
transaction. Crossing UTC midnight cannot replenish it. This does not change
policy period/currency or reset/import old ledgers. Keep the manifest/keys/ledger
together; do not delete/edit the authorization to extend a test window. All worker
processes must use the same approved configuration; the combined local launcher
supplies it to its managed worker. This is not production distributed acceptance.

The duration is an operator-selected local test policy. The current 7200-second
implementation bound reflects the earlier two-hour validation choice; it is not
a paid-model requirement, login-token lifetime, per-student quota or formal-course
restriction. R2 retention and R3 periodic/cumulative budgets are independent.
Continuous local development can instead use **amount-only mode**, with no
inference deadline and the same finite cumulative cap. Stop the installation,
then run `./start-belay.ps1 -UseAmountOnlyBudget` from the repository root. This
explicit transition archives an existing window and pins its original cap in
`runtime.json`; it does not change the database, prices, policy version or usage.
It refuses pending grants and active/queued work. An unknown task/hold stays
unknown and is never replayed. `check` reports `state: disabled, mode: amount_only`;
normal start/stop commands remain unchanged. This supersedes the earlier
[fixed-window discussion](budget-policy.md).

For new profiles, configure zero window/expiry plus an approved finite cumulative
cap, prepare the new installation once, then persist amount-only mode with that
same command. Persisted mode/cap override later env changes for API and worker.
Converting back to a bounded authorization needs a separate reviewed transition;
deleting the manifest is not a supported mode switch. The existing timed mode
and additional-money authorization workflow below remain for timed profiles.

To use a supported real provider, configure its environment fields and credentials
privately, install its SDK, and supply/review the correct control policy. Neither
the launcher nor prepare makes a paid test call. An actual Ask/Run feedback or
eligible queued job will. No hosted-provider acceptance test was performed and
the running paid preview was not reconfigured. One full-suite attempt mistakenly
set the legacy presence-based `RUN_LLM_EVALS` gate to `0`, which attempted the
default localhost inference endpoint and returned503; the integration summary
records this separately from the explicitly offline adapter tests.
The prior DeepSeek paid manual observation belongs to its unchanged dedicated
preview, not proof of this entry's live acceptance. No production load/SSO/backup
operations/deployment or arbitrary provider certification is claimed.

## Offline verification

```powershell
Set-Location C:\Projects\EduCloud-Ecosystem\belay\backend
Remove-Item Env:RUN_LLM_EVALS -ErrorAction SilentlyContinue
python -m pytest tests/test_controlled_runtime.py tests/test_provider_capabilities.py tests/test_saved_jobs.py tests/test_jobs_worker.py -q
Set-Location ..\frontend
npm ci --ignore-scripts
npm test
```

Tests provision only disposable directories/databases and mock SDK create calls;
they cover signed auth, original-principal revocation, actual local runner and
three original exercises, saved/unsaved publication, dedup/GET recovery, timeout
holds and budget settlement. Frontend tests cover automatic Run feedback and
same safe render/recovery paths. This is offline layered integration evidence,
not an authenticated browser claim or a newly started demo service.


## Explicit additional local validation authorization

This existing command is for **additional money**, not a time-only extension.
It requires a positive additional amount and forfeits old unspent allowance.
Do not put the remaining balance into `additional_microunits` to bypass that
contract. Preserving the existing cumulative cap while changing only time needs
the separate, explicitly reviewed extension mode proposed above.

For an expired one-time authorization, stop the matching installation first and
review all queued/running/cancel-requested work. Do not replay unknown jobs.
`authorize-window` accepts an operator-authored authorization JSON and a new
policy version. It never prepares/migrates the DB, changes deployment, imports
another ledger or starts listeners. It only permits version/currency-limit
changes through the existing `Ledger.update_policy` contract; provider pricing,
token/runner limits, identity and retention remain unchanged.

Example authorization fields (numbers are examples, not an automatic grant):

```json
{"id":"approved-local-validation-unique-id","additional_microunits":100000,
 "seconds":7200,"unused_balance":"forfeit","expected_consumed_microunits":48223,
 "expected_policy_version":"previous-reviewed-policy-version"}
```

Set all four policy currency limits to historical settled consumption + explicitly
approved additional amount (148223 in this example). Expired old unused balance
is forfeited; unresolved holds continue to encumber the new allowance. Keep the
same deployment/DB and unchanged other policy fields. A changed ledger or active
queue blocks the update. The authorization ID is idempotent and conflicting reuse
is rejected. The database policy and manifest are not naturally atomic: after a
DB-commit/manifest-write fault the old expired manifest fences model dispatch;
retry the identical authorization to finish publication without another grant.
The pending policy version is checked on startup. The launcher is a single local
operator host; this is not a distributed policy-update protocol.

```powershell
Set-Location C:\Projects\EduCloud-Ecosystem\belay\backend
python -m app.controlled_runtime authorize-window --data-dir ..\deployment\local\controlled-runtime --env-file ..\deployment\local\controlled-config\.env --credentials-env-file .env --policy ..\deployment\local\controlled-config\additional-policy.json --authorization ..\deployment\local\controlled-config\additional-authorization.json
python -m app.controlled_runtime check --data-dir ..\deployment\local\controlled-runtime --env-file ..\deployment\local\controlled-config\.env --credentials-env-file .env
```

`check` shows an unarmed two-hour window. First **manual** start fixes its UTC
start/end in runtime.json before worker dispatch. Restarts reuse that deadline;
only a separate explicit authorization after expiry can create another window.
Local authorization/config/DB/key files stay ignored; do not commit them.
