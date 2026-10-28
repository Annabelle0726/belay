# General controlled runtime integration

## G1 — verified baseline and implementation scope

Branch: `fix/run-code-tutor-feedback`, starting HEAD `1899de0`. Preserve the
existing uncommitted frontend rendering/waiting work and the unrelated untracked
`controls-integration-review.md`. No branch/history/main/remote changes.

Core already contains signed R1 identity and original-principal rechecks, R2
optional saving/revisions/deletion/expiry, R3 admission/idempotency/ledger/data
publication, and `AskAdapter`/`run_one`. `local_dev --controlled-stub` wires these
with a synthetic model. The dev-client's animation/accessibility and safe
Markdown changes are generic frontend changes, not provider-specific behavior.

Only ignored `deployment/local/run-feedback-verification` contains the paid
DeepSeek preview helper, dedicated PS launchers, fixed model/endpoint/thinking,
30-second timeout wrapper, fixed one-hour validation window and USD0.10 policy.
Those local files and the prior manual test evidence stay intact. Their settings
are not product defaults or production approval.

| Capability | Location / repository status |
|---|---|
| Signed identity / current authorization | `backend/app/auth.py`, already core |
| Optional saved conversation lifecycle | `backend/app/conversations/`, already core |
| Controlled submission, ledger, Ask worker, saved publication | `backend/app/controls/`, already core |
| Provider registry and SDK adapters | `backend/app/agent/llm.py`, already core; narrowly extended here |
| Shared waiting animation / safe Markdown | `frontend/dev-client.*`, `conversation-client.js`, `vendor/`; preserved uncommitted common frontend work |
| Fixed DeepSeek profile / one-hour USD0.10 validation | `deployment/local/run-feedback-verification/deepseek_preview.py`, `start-deepseek-preview.ps1`, `stop-deepseek-preview.ps1`; ignored local files |
| Local audit / stub preview handoff | Same ignored directory's `implementation-summary.md`, `stub-validation-plan.md`, audit JSON and dedicated stub launchers |
| General config / lifecycle entry | New `backend/app/controlled_runtime.py` and `deployment/controls/controlled-runtime*`, generic PS wrappers; intended tracked integration files |

Actual registry: `openai_compatible` (Chat Completions SDK), `anthropic` (Messages
SDK), `bedrock` (documented unimplemented stub). Compatibility with an arbitrary
API, model, schema or reasoning feature is not promised. The existing controlled
worker is provider-independent; the missing piece is a supported runtime assembly.

Implementation: (1) tracked env-configured prepare/migrate/check/start/stop entry
with explicit synthetic identity, shared local R2/R3 SQLite, approved policy and
cleanup/worker lifecycle; (2) narrowly scoped adapter capabilities and bounded SDK
timeouts with retries disabled; (3) isolated SDK-shaped integration and existing
frontend/backend regression. Start must not initialize/recreate/migrate data or
reset authorization, keys or budget. Existing R1/R2/R3 protocols are reused.

G1 checks: repository/code/local summary read; no model call, service changes or
database writes. Tests pending implementation. No commit.

## G2 — general runtime assembly and explicit initialization boundary

Files: `backend/app/controlled_runtime.py`, `config.py`, `store/db.py`,
`controls/jobs_worker.py`, `deployment/controls/controlled-runtime.env.example`,
`controlled-runtime-policy.example.json`, generic start/stop PowerShell wrappers,
and `backend/tests/test_controlled_runtime.py`. No commit.

New tracked entry assembles the existing APIs/AskAdapter/worker. `prepare` only
accepts a new directory; `migrate` is explicit and refuses changed installed
policy; `check/start` require all schemas, deletion ledger, encryption/identity
keys and existing policy. Start disables SqlStore's legacy automatic create_all.
No authorization/key rotation or budget initialization on start. Stable unique
issuer per installation prevents old recovery pointers crossing new databases.
R2/R3 use the same SQLite URL; policy/keys/private files stay in ignored data dirs.
The loopback host issues real signed synthetic credentials, not production SSO.

Worker lifecycle includes controls data cleanup, R2 expiry/deletion cleanup even
when saving is disabled, fatal-worker supervision and cooperative stop. Stop
does not kill by port/PID, erase pointers, refund holds or replay unknown jobs.
Eligible queued jobs can dispatch after startup; no inference probe is made.
General policy is operator supplied; example is explicit unmetered synthetic
pricing, finite budgets (USD0.10/period) and no vendor/model defaults in entry.

Initial new suite:9 pass/8 fail. A Windows binary-write newline issue caused key
byte mismatch; fixed binary exclusive writes plus normalized public-key compare.
An isolated test SQLite handle needed explicit close before deleting that test
file. Rerun15 pass/2 SDK scenarios pending: the network guard initially blocked
Windows asyncio's internal loopback socketpair; guard now permits only loopback
and rejects external traffic. No actual preview restart or model call. Runtime
live lifecycle and complete regression pending G4. Existing data untouched.

## G3 — provider capabilities, accounting and conservative failure behavior

Files: `backend/app/agent/llm.py`, `config.py`,
`backend/tests/test_provider_capabilities.py`, SDK child scenario test. No commit.
Both existing live SDK adapters now have configurable finite request timeout;
SDK automatic retries stay0. OpenAI-compatible capability fields explicitly
select JSON response format, thinking mode and final-content-only extraction.
Thinking mode is applied to every physical attempt including400/422 fallback
and JSON repair, without inspecting endpoint/model names. Anthropic receives
only its own thinking/auth/request/usage behavior. Existing model_call still
accounts separately for each attempt; missing usage/timeout holds are retained.
Cache tokens are counted conservatively in Anthropic input usage.

Registered the already-existing local demo provider as explicit `local_stub`;
general entry does not replace another provider's registry class. Bedrock is
rejected before runtime preparation because its adapter is unimplemented.
Metered profiles require positive explicit policy price bounds and all scopes
finite; unmetered pricing requires an explicit operator declaration. Telemetry
price fields do not enforce budgets or establish vendor invoice prices.

Verification: existing provider/execution suite23 passed; new capability suite
8 passed/0 failed/0 skipped (mock SDKs, no inference network). Covers opt-in
isolation, JSON fallback/repair accounting, final-content-only, effective thinking
bound/cache usage and both adapters' timeout/missing-usage holds. Full regression
and complete SDK-backed controlled HTTP scenarios are pending G4.

## G4 — isolated integration, lifecycle and regression verification

Files: `tests/test_controlled_runtime.py`, `tests/controlled_runtime_scenario.py`,
`tests/test_provider_capabilities.py`, canonical `controlled-runtime.md`, root /
frontend README links and CI frontend dependency installation. No commit.
Preserved frontend files: `conversation-client.js`, `dev-client.js/html`, their
tests, pinned package/lock and local renderer/highlighter vendor assets. The
waiting/Markdown implementation remains common to all selected providers.

Configuration hardening: an explicit env file overrides inherited non-secret
settings, so a stub profile cannot inherit a paid PROVIDER accidentally. Process
API credentials retain priority; no credential is copied into runtime receipts.
SDK availability is checked without constructing/calling it. OpenAI capability
validation applies only to OpenAI-compatible selection. The default example has
synthetic zero prices; metered selection must supply reviewed positive bounds.

Real registered adapters (OpenAI-compatible, Anthropic, local_stub), signed HTTP
identity, original three-exercise pack, actual sandbox runner and existing R3
worker/R2 publication are tested with disposable shared SQLite installations.
SDK responses are mocked and an external-network guard is installed. Coverage:
saved/unsaved Run then feedback, Ask-style jobs, duplicate POST and single
execution, GET recovery, two saved messages/revision2, original-principal
revocation despite another subject retaining the same scope, SDK timeout unknown
hold/no replay, budget rejection before another send and separately settled
physical attempts. UI automatic submission/render/refresh behavior is covered by
the existing frontend tests; this is layered integration, not a live browser test.

The first SDK scenario failures came from a test-only saved request containing
the unsaved `event` field. Corrected the test to use the existing R2 contract;
both real adapters then passed. Managed start/stop uses mocked sockets/servers,
not service launch: matching cooperative stop and fatal worker supervision are
verified. A separate real worker-thread test verifies R2 cleanup with new saving
disabled and content-free fatal exit. No launcher override of provider classes.

Verification in progress: frontend94 passed/0 failed/0 skipped; targeted runtime
and adapter suite rerunning after adding provider-config isolation and worker
cleanup tests. Initial full backend run:781 passed/1 failed/16 skipped. This was
an invocation error: setting RUN_LLM_EVALS=0 enabled the legacy presence-based live
eval gate. It attempted one SDK send with default openai_compatible/llama3.2,
localhost:11434/v1, placeholder EMPTY credential and returned503. No model result
was obtained; this was not a DeepSeek preview audit or proof of no attempted
inference. No evidence of a paid-provider call; historical service-side execution
is not independently verified. The complete rerun removes that variable.

Ruff/format passed. One concurrent mypy run hit a Windows shared-cache permission
error, while app/tests type checking passed; default full mypy reruns with an
independent ignored cache. Final counts and remaining limitations follow below.

Existing8003/5176 preview remains PID10832; no8004/5177 listener was started.
No old DB/auth/key/.env/task pointer was initialized, cleared or migrated. The
historically rejected persistent demo launch is not retried via another command
or tool; the guide supplies foreground commands for manual operator execution.

## Final scope and verification record

Latest targeted suite:33 passed,0 failed,0 skipped (runtime/provider tests).
The provider-isolation refinement initially exposed one stale test assumption:
an invalid OpenAI-only flag was expected to reject local_stub. Changed that
negative test to select OpenAI explicitly and added two positive cases proving
Anthropic/local_stub ignore the irrelevant flag. Final targeted run is clean.

Complete offline backend regression:782 passed,0 failed,17 skipped (799 total).
Skipped:10 PostgreSQL schema/transaction/multiprocess cases (no disposable DSN),
6 verifier-contract schema cases (sibling checkout unavailable), and1 opt-in live
model benchmark. The full run and33-test final targeted run overlap; their counts
must not be added. Two newly added provider-isolation cases were verified in the
final targeted run after full-suite collection. Frontend:94 passed,0 failed,
0 skipped. Ruff check and format pass across162 files; full default mypy passes
across155 source files using an independent ignored cache. Both PS wrappers parse
with0 errors; `git diff --check` passes. Reports stay ignored under the existing
local verification directory; no secrets/database/logs are proposed for Git.

Implemented: generic environment-driven local controlled runtime, explicit
prepare/migrate versus checked start, synthetic signed identity, same R2/R3 SQLite
transaction boundary, existing policy/worker and cleanup, cooperative shutdown,
explicit adapter capabilities, conservative timeout/missing-usage handling and
the preserved common UI animation/Markdown behavior. No R1/R2/R3 replacement,
cancel button, new term rules or revised save/retention/research-consent contract.
All work remains uncommitted on the original feature branch; no history rewrite,
main update, push or deployment. Unrelated untracked review document untouched.

Not verified: newly started generic entry in a real authenticated browser,
hosted API/model acceptance, PostgreSQL cross-process validation in this machine,
institutional SSO, production load/fairness/capacity/operational backup readiness.
Bedrock remains unimplemented. Generic combined launcher is intentionally local
loopback/SQLite/synthetic identity; actual hosted deployments provision identity
and the existing app/worker separately. SDK-shaped success is not proof of live
vendor compatibility or invoice cost. No service is claimed started by tests.

Local operation: follow `controlled-runtime.md` to copy fresh private stub config,
prepare a NEW data directory, run check, then manually run the generic foreground
PowerShell launcher. Defaults: frontend5177/dev-client.html, API8004, one managed
worker. Run each original exercise, inspect execution/check output separately
from the labelled local stub reply; also test Ask, saving off/on and refresh.
Unknown old pointers are never cleared/replayed; the new unique issuer isolates
recovery scope. Stop with Ctrl+C or matching generic stop wrapper and wait for
foreground exit. Current8003/5176 preview stays unchanged;8004/5177 are not yet live.

## G5 — discoverable team onboarding documentation

Goal: identify the general code/launcher and make usage discoverable from the
repository home. Added `deployment/controls/README.md` with an entry-file map,
dependency prerequisites, portable repository-root first-use preparation, daily
start/stop, provider/policy boundaries and separate Run/check/feedback validation.
The first-use block stops before copying or preparing if config/data already
exists. Root/frontend README link to it; the detailed guide links back. Existing
uncommitted implementation/frontend work and the unrelated review remain intact.

Scope: documentation only; no DB/config/provider/service changes, model calls,
Git commit or push. Verification: local document link targets and PowerShell
block syntax checked, plus `git diff --check`; no executable startup/setup
commands run. Backend/frontend suites not rerun for this documentation-only step.
Remaining: actual fresh-clone/manual startup acceptance by a team member and the
previously recorded live-provider/PostgreSQL/production validation limits.

G5 follow-up: root README now contains the actual first-use preparation, start
and stop PowerShell blocks plus URLs, without requiring file navigation. The
controls README places executable usage instructions before its source-file map.
Read-only path check confirmed the suggested general installation/config are not
yet present on this machine; commands are instructions, not a startup claim.
PowerShell blocks syntax-checked without execution; documentation-only, no commit.

## G6 — requested DeepSeek configuration; blocked before paid activation

2026-10-10 read-only inspection: generic manifest retains original deployment ID,
8004/5177 and same common database. Active env/receipt: local_stub, unmetered,
synthetic zero-price policy, PID25660, managed worker receipt. Generic check passed
without model calls. One completed job/three model attempts/five settled resource
attempts, zero currency charge. Receipt is not live per-thread health certification.

Old DeepSeek preview audit now has four completed jobs/12 model attempts and
USD0.037221 settled, zero unresolved monetary holds; original one-hour window is
expired. Earlier USD0.028359 observation was an earlier snapshot, not current use.
Remaining nominalUSD0.062779 cannot be silently renewed/transferred to this host.

Prepared ignored local `controlled-config/deepseek.pending.env`, positive-price
`deepseek.pending-policy.json` and `deepseek-handoff.md`. These do not replace the
active env or installed policy. Reuse openai_compatible/deepseek-flash both tiers,
official endpoint, thinking disabled, JSON response format, final content only,
30-second timeout. Official pricing checked2026-10-10: Flash peak uncached input
USD0.30/M, outputUSD1.20/M. Integer ledger uses conservative1/2 microunits/token;
not invoice-exact/cache-discount accounting. Pending monetary caps are0, not a
grant of new funds. Original currencies, periods, DB, auth, keys, scopes preserved.

Structural candidate checks passed using a fake process-only check credential and
SDK construction/network creation blocked. Full metered check correctly failed
against still-installed stub zero prices. Credential validity, paid readiness,
worker reload and real response remain UNVERIFIED. No SDK completion, migration,
prepare, ledger mutation, process stop/start, push or commit occurred.

Required next decision: explicit reauthorization of old remainderUSD0.062779 or
new proposedUSD0.05, with a fixed one-hour window. Generic daily-period policy
alone cannot enforce a once-only window; before activation a provider-neutral
absolute inference deadline is needed. No schema/new deployment ID is needed for
the price update; use existing update-policy after a matching manual stop and
preserve old attempt snapshots. User must input credentials locally. Waiting for
budget/window authorization; do not mark configuration or real replies complete.

## G7 — authorized remaining budget and general-runtime DeepSeek configuration

User explicitly reauthorized old remainderUSD0.062779 for one fixed hour; old
settledUSD0.037221 plus this allowance stays within originalUSD0.10. No additional
funds/new deployment ID/currency/period/schema were authorized or introduced.

General changes: `config.py`, `controlled_runtime.py`, `controls/runtime.py`,
`controls/ledger.py`, `tests/test_inference_window.py`, runtime tests and generic
env/reference docs. Optional first-start deadline/cumulative cap are persisted in
the installation manifest, reused on restart and checked before each model send.
Already-sent replies settle normally; timeout holds remain. Cumulative monetary
cap is checked within the reservation transaction across ALL periods, preventing
a UTC-midnight refill during the approved hour. No provider/model hardcoding or
alternate page/launcher. Defaults preserve existing unbounded profiles unless the
optional authorization fields are configured; production multi-process use needs
consistent provisioning and separate acceptance, not inferred from local tests.

Applied local changes only under ignored controlled-config: active .env selects
openai_compatible, official endpoint, deepseek-flash both tiers, thinking disabled,
JSON/final-only, timeout30; policy has positive conservative1/2 microunits/token,
62779 currency caps. Optional total cap62779/window3600 configured. Original files
backed up privately; explicit budget authorization and read-only audit saved.
No key copied/read/printed into config, chat or Git. Same DB, auth, encryption,
manifest identity and saving/retention/research-consent behavior preserved.

Stopped only confirmed general PID25660 via matching cooperative stop; receipt
removed and8004/5177 no longer listen. Old8003/5176 PID10832 untouched. Then used
existing `app.controls.cli update-policy` to install controlled-deepseek-20261010-v1.
Hash comparison: only control_configuration changed; all pre-existing rows in
other tables unchanged. No prepare/init/migrate, cleared pointers or task replay.

Final static full check passed with an explicit fake process-only check key and
SDK/network construction blocked: real credential NOT validated; models correct,
positive policy/price versions, total62779, window unarmed3600, inference_probe=false.
The agent did not start services/arm the real window or send a model request.
Actual worker readiness, provider connectivity and real replies remain unverified.
Manual first start will persist the window before dispatch; repeated check does
not consume or renew it. Human receives full hidden-key/check/start/stop commands
in ignored `controlled-config/deepseek-handoff.md`, using the SAME general launcher.
Read-only inspect-runtime.py joins attempts.operation to jobs.id, prints metadata
only, and separates old synthetic attempts from the positive price version.

Validation: initial new window suite hit Windows fsync read-only descriptor error;
fixed writable descriptor before atomic manifest replace. Final related suite:
151 passed,0 failed,9 PostgreSQL tests skipped (no isolated DSN),160 total across17
test files. Includes lifetime-cap settled/unknown carryover and concurrent SQLite
reservation test. Ruff/format pass163 files; targeted mypy6 files pass. Existing
frontend/full backend/PostgreSQL not rerun this step; frontend unchanged. No commit,
push or deployment. Previous full regression evidence is historical, not rerun
evidence for this new guard. Remaining: user's real-key check/manual browser test,
live managed worker confirmation, provider invoice comparison and PG acceptance.

### Credential-file follow-up (2026-10-10)
Added explicit supplemental credential-file loading to the generic CLI/PowerShell
entry, with credential-only filtering and process-first precedence. Missing-key
prompt is conditional; existing keys are reused without copying. Team copy/paste
commands documented in deployment/controls/README.md. No prepare, policy change,
DB write, authorization renewal, service start or inference call. Detailed bug
validation is local in deployment/local/controlled-config/run-error-key-summary.md.

### Conversation flow and explicit additional authorization (2026-10-10)
UI restores student/Sol bubbles; execution reports stay left. Latest live reply
alone owns a collapsed inline Glass Box; new Run/Ask removes old signals while
keeping answers. Desktop columns share bounded height, feed scrolls internally.
Existing safe Markdown/highlighting remain on live and recovery paths.
Student exception context includes student-only line, accurate syntax/runtime
classification and grounded feedback instruction. Offline adapter scenarios
cover success, ValueError, SyntaxError and failed checks with saving on/off.
Generic authorize-window implements a user-authored incremental grant via existing
update_policy, preserving spend/unknown holds, forfeiting expired unused allowance,
idempotent ID, crash recovery and fixed first-manual-start deadline up to7200s.
Detailed step evidence/status is local in controlled-config/conversation-flow-summary.md.
No commit/push/deployment; paid browser error feedback remains for human validation.
