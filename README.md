# peer-tutor-framework

A generalizable, evaluation-first peer-tutor framework. Its defining property: the
tutor cannot leak an exercise solution because a deterministic, executable Governance
gate runs the draft through the active domain's grader and strips any full solution,
rather than merely asking the model not to.

> The repository name `peer-tutor-framework` is a placeholder. The settled name
> is **Belay** (see `../educloud/SYSTEM.md`); it is applied in a single atomic
> commit at the publish step.

## What it is

The tutor runs an evaluation-first loop per turn: a Planner picks one pedagogical
move, a Peer-Reasoner writes the message, a Self-Evaluation critiques it against a
stance rubric, a bounded refine fixes a failing draft, a deterministic Governance gate
runs last, and Memory merges what the student now grasps. The reference domain is
general data science (the "Robin" pack). This framework is original; its first
implementation was built within a quantum tutor, and the domain-agnostic core was
extracted from that codebase. The quantum-specific application stays in its own
repository and is not part of this framework.

Three properties distinguish it:

- Deterministic governance. The no-leak rule is an executable gate, not a prompt
  instruction. Leak-detection has a ground-truth oracle (the pack's grader plus the
  known solution), so the gate decides post-hoc and is supreme over everything,
  including a student goal that demands the answer.
- Privacy by architecture. Identity is a pseudonymous host id only (for example
  `gh:12345`); PII is rejected at the sidecar boundary; there is no write path to
  grades and no rankings. Goals and reflections are pseudonymous and never surfaced to
  an instructor.
- Compute-agnostic, self-hosted first. The default provider is `openai_compatible`
  pointed at a local Ollama or vLLM endpoint, so the tutor can run entirely on
  institutional compute with no external API in the data path.

## Authentication required

All learner/resource API routes now require a short-lived signed bearer plus
operator-owned institution/class/learner and assignment-version grants. The
production default refuses protected requests with missing configuration (503).
Local/test modes must be explicitly selected and also require credentials.
Set up the [identity contract and authorization file](docs/authentication.md)
before following the quickstart. Health checks remain public.

## Quickstart

### Controlled Run code / Ask Sol (PowerShell)

Open PowerShell in this repository's root with your Python environment activated.
For **first use only**, copy and run this entire block. It prepares a new local
model-stub installation; it refuses existing config/data rather than overwriting
them. It does not start services or call a real model.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $belayRoot = (Get-Location).Path
    if (-not (Test-Path './backend/app/controlled_runtime.py')) { throw 'Run from the Belay repository root.' }
    $configDir = Join-Path $belayRoot 'deployment/local/controlled-config'
    $dataDir = Join-Path $belayRoot 'deployment/local/controlled-runtime'
    if ((Test-Path $configDir) -or (Test-Path $dataDir)) { throw 'Already configured or partially prepared; retain existing files and inspect them before proceeding.' }
    python -m pip install -r ./backend/requirements.txt -r ./backend/requirements-packs.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    New-Item -ItemType Directory -Path $configDir | Out-Null
    Copy-Item ./deployment/controls/controlled-runtime.env.example (Join-Path $configDir '.env')
    Copy-Item ./deployment/controls/controlled-runtime-policy.example.json (Join-Path $configDir 'policy.json')
    Push-Location ./backend
    try {
        python -m app.controlled_runtime prepare --data-dir $dataDir --env-file (Join-Path $configDir '.env') --policy (Join-Path $configDir 'policy.json') --api-port 8004 --frontend-port 5177
        if ($LASTEXITCODE -ne 0) { throw 'Preparation failed; do not reinitialize existing data.' }
    } finally { Pop-Location }
}
```

**Daily commands** for an already prepared installation, from the repository root:

```powershell
.\start-belay.ps1 -Check
.\start-belay.ps1
```

Defaults read `deployment/local/controlled-config/.env` and, if present,
credentials only from `backend/.env`. The selected provider/models come from
configuration; an existing profile may use paid inference. Only missing keys
prompt securely. Check makes no model calls and reports queued work and expiry.
After successful start,
open **http://127.0.0.1:5177/dev-client.html**; API: **http://127.0.0.1:8004**.
The command runs API, frontend and worker together in the foreground. Default
feedback in a fresh example installation is labelled `Local model stub`; existing
configurations are retained. Wait for `ready:true` and `worker_alive:true`;
`checked:true` alone is preflight. Eligible queued work can execute on start;
unknown tasks are not automatically resubmitted.

**Stop:** press **Ctrl+C** in the starting terminal, or run this from a second
PowerShell at the repository root:

```powershell
.\stop-belay.ps1
```

Wait for the starting terminal to exit. Start does not initialize/migrate/reset
data; stop does not erase task records or refund unknown usage.
Start never renews a persisted authorization. An approved, unarmed window starts
once on first launch. An expired window requires explicit review, not another
prepare. Optional `-DataDir`, `-EnvFile`, `-CredentialsEnvFile` select another
prepared installation. Model changes also need reviewed prices and budget policy,
not just a new key. See the team README below for precedence and troubleshooting.

The inference time window is an operator-selected **local testing policy**,
independent of API credential lifetime, student budget limits and saved-dialogue
retention. Two hours was a temporary validation choice, not a model-provider or
formal-course requirement. For continuous local development, a **cumulative
amount-only budget** needs no short expiry or renewal. To explicitly convert an
existing finite authorization, stop its host and run once from the repository root:

```powershell
.\start-belay.ps1 -UseAmountOnlyBudget
.\start-belay.ps1 -Check
```

The conversion archives the old deadline, pins the **same cumulative ceiling**,
and leaves the database, consumed money and unknown reservations unchanged. It
does not start services, grant money or change prices. Active/queued work and
pending authorizations require review before conversion. Unknown tasks remain
unreplayed. The normal `./start-belay.ps1` and `./stop-belay.ps1` commands then
remain unchanged. An exhausted amount budget still blocks inference.

For a new amount-only profile, configure `CONTROLS_INFERENCE_WINDOW_SECONDS=0`,
`CONTROLS_INFERENCE_EXPIRES_AT=0` and an explicitly approved finite
`CONTROLS_INFERENCE_TOTAL_MICROUNITS`, prepare **only that new installation**, then
use the same conversion command to persist the ceiling. One USD is 1,000,000
microunits. Existing installations take the ceiling from their saved authorization,
not a larger env value. The per-scope policy limits continue to apply as well.
Bounded profiles still support fixed windows up to 7200 seconds, persisted on
first start and never renewed by restart. See the [team README](deployment/controls/README.md)
for configuration precedence and mode-change constraints.

**Developer budget versus teaching quota:** local amount-only testing uses an
explicit finite cumulative budget with no short renewal deadline. It is not a
student allowance. Raising it requires approval of the additional money and
associated resource limits; changing only the key or scoped policy cannot raise
the manifest's pinned ceiling. The [local budget proposal and future course
quota requirements](deployment/controls/budget-policy.md) record
the current audit and pending recommendation, not active new settings.
Formal teaching is a separate future requirement: configurable learner quota
periods during valid course access, with spending still accumulated against the
class/course total and all ledger history retained. That policy and its ownership
are to be agreed with Greg; no new periodic quota or admin UI is implemented.

For the newer **local short-period + weekly** proposal, see the
[current budget plan and verification summary](deployment/controls/budget-policy.md).
The optional coordinator checks both fixed windows plus existing scope/cumulative
limits. A quota refresh does not add funds or erase historical/unknown usage.
Local budget changes require explicit authorization. A **new explicit local approval
on 2026-10-11 has now been applied**: USD5 additional funding, cumulative ceiling
USD5.148223 without expiry, USD1 per six hours and USD5 per week. These are that
local installation's approved values, not repository/provider/student defaults.

Its fixed timezone is **Asia/Shanghai (UTC+08:00)**: six-hour buckets begin at
00:00/06:00/12:00/18:00; weeks begin Monday 00:00. Short refresh never resets week
usage; week refresh never resets cumulative usage or grants new money. Restart
does not change these boundaries. Both windows and all other budget controls
must pass. Other resource caps remain unchanged. See the
[applied authorization and verification summary](deployment/controls/budget-policy.md)
for preserved ledger evidence and the manual restart commands. Formal
student/course quota rules remain separate and unimplemented.

The deployment allowance is **shared across providers, models and tiers** in
the same controlled installation. Planning, generation, evaluation, revision,
format fallback and JSON repair each reserve and settle through `model_call`.
Changing `PROVIDER` or model names does not create another quota or reset history.
Keep the same database, deployment ID and approved cumulative cap on all workers.
The policy uses one conservative input/output price bound covering every selected
model; it is not an automatic vendor price catalogue. Review these bounds when
switching models. `LLM_BILLING_MODE=metered` rejects zero/missing prices before
dispatch; free/self-hosted inference requires explicit `unmetered` configuration
and still obeys token/resource limits. Missing usage retains a reservation.
See the [shared-provider audit](deployment/controls/shared-provider-budget-audit-summary.md)
for simulated-adapter coverage and remaining verification limits.

For the integrated **controlled Run code / Ask Sol / optional save and recovery**
page, start with the [team setup and launch README](deployment/controls/README.md)
(first-time preparation, daily start/stop and code entry map). The
[controlled runtime guide](deployment/controls/controlled-runtime.md) documents
provider configuration, migrations and operational boundaries.
Its tracked `app.controlled_runtime` entry separates prepare/migrate from start,
assembles identity/shared R2-R3 database/policy/worker/cleanup, and selects an
implemented provider from backend environment. The default example is a local
model stub. The older container/source quickstart below does not itself provision
these controlled-job prerequisites.

The fastest path is the container, which is SQLite-default and points at a local
OpenAI-compatible model endpoint with no external API.

```bash
docker compose up --build                    # SQLite + openai_compatible
docker compose --profile postgres up --build # Postgres opt-in (scale)
```

The container CMD runs the preflight doctor informationally and then serves on port
8000. To run the doctor directly:

```bash
cd backend && python -m app.preflight                 # checks config, store, provider
cd backend && python -m app.preflight --skip-provider # skip the endpoint probe
```

Preflight prints `[PASS] <check>` / `[FAIL] <check>` for `config`, `store`, and
(unless skipped) `provider`, then `preflight: OK` or `preflight: FAILED` with a
non-zero exit on failure.

To run the suite and the local server from source, see `VALIDATION.md` (the canonical
runbook); env knobs are defined in `backend/app/config.py`. The operationally relevant
ones:

| Env var | Default | Purpose |
|---|---|---|
| `PROVIDER` | `openai_compatible` | Inference provider; also recorded in the trace |
| `OPENAI_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible endpoint (Ollama/vLLM) |
| `OPENAI_API_KEY` | `EMPTY` | Key for the endpoint (local endpoints ignore it) |
| `MODEL_FAST` | `llama3.2` | Concrete model for the fast tier |
| `MODEL_STRONG` | `llama3.2` | Concrete model for the strong tier |
| `OPENAI_REASONING` | `0` | Send `reasoning_effort` (strong tier) only if on |
| `TUTOR_PACK` | `datascience` | Active domain pack |
| `STORE_BACKEND` | `sql` | `sql` (durable) or `memory` (ephemeral) |
| `DATABASE_URL` | `sqlite:///./qimvp.db` | Store DSN; a Postgres DSN opts into Postgres |
| `MAX_REFINE` | `1` | Reasoner revisions after a failing self-eval |
| `TAU_ESCALATE` / `MAX_ESCALATE` | `0.55` / `1` | Re-run at higher effort when under-confident |
| `TAU_ABSTAIN` | `0.35` | Peer-only honest abstention floor |

## Adding a domain pack

A pack implements the `DomainPack` protocol (`backend/app/core/domain/pack.py`):
`curriculum`, `get_exercise`, `run`, `program_signature`, `verify_worked_example`,
`misconceptions`, `leak_evidence`, and optional `knowledge`. Start from
`backend/app/packs/_skeleton/` (a dependency-free echo pack used for core-only tests)
and model a real one on `backend/app/packs/datascience/` (the reference pack: a
taxonomy, a curriculum, declarative grading specs, a misconception library, and
combined leak evidence). Register the pack's factory in
`backend/app/core/domain/registry.py` and select it with `TUTOR_PACK`. Core never
imports a pack at module load; the dependency arrow points from packs to core.

A pack's optional `knowledge()` is backed by the domain-reusable corpus pipeline
(`backend/app/knowledge/`): a license-gated ingestion step produces a normalized,
pack-scoped corpus (only public-domain / CC0 / CC-BY / MIT / Apache-2.0 / BSD content is
admitted, with per-passage license and attribution recorded), and a separate lexical (BM25)
indexing step serves it behind the unchanged `KnowledgeBase` contract. Retrieval is lexical
now; a local-embedding vector index can be added later behind the same contract with no
re-ingest. Only a tiny seed corpus ships in-tree; ingesting real sources is a later operator
step. Retrieved passages pass through the same deterministic leak gate as a generated draft,
so retrieving an answer is not a loophole. See `ARCHITECTURE.md` and `ROADMAP.md`.

## Pointing at a provider

`PROVIDER` selects the provider; the fast/strong tier policy (Planner fast, Reasoner
strong, Self-Evaluator fast) lives in core and is provider-agnostic. Only the
tier-to-model mapping is per-provider config.

- `openai_compatible` (default, self-hosted first): set `OPENAI_BASE_URL`,
  `MODEL_FAST`, `MODEL_STRONG`, and `OPENAI_API_KEY`. Sends no reasoning parameter
  unless `OPENAI_REASONING=1`, so it works with ordinary local models.
- `anthropic` (hosted convenience): set `ANTHROPIC_API_KEY`; tiers default to
  `claude-haiku-4-5-20251001` (fast) and `claude-sonnet-4-6` (strong); extended
  thinking is on by default.
- `bedrock`: a documented stub, not live. Its Amazon Nova tier mapping is testable but
  a call raises.

## Quad sidecar

A versioned HTTP/JSON sidecar exposes the existing tutor loop to the EduCloud Quad
control plane at base path `/quad/v1` (`backend/app/integrations/quad/`, mounted on the
main app). It imports core only, advertises its posture at `/quad/v1/capabilities`
(pseudonymous identity, grades read-only with no write path, Apache-2.0), runs one
tutor turn at `/quad/v1/turn`, and rejects PII at the boundary with a 422.

## Behavioral benchmark

A portable, pack- and provider-parameterized benchmark lives in
`backend/evals/behavioral/`. Run it from `backend/`:

```bash
python -m evals.behavioral --pack datascience [--provider P] [--repeats N] \
    [--judge-provider P] [--temperature 0] [--families a,b,c] [--no-judge] [--out report.json]
```

`no_solution` and `never_leak` are deterministic gate verdicts (the harness runs
`pack.leak_evidence` on the emitted text), not LLM rubrics. Qualitative families use a
separate strong judge configured via `JUDGE_PROVIDER` / `JUDGE_MODEL`; if the judge
model equals a tutor model under test the report marks those families
`credible: false` / `self_judged: true`. The deterministic axes are credible today;
the strong-judge run at higher repeats is pending.

## License

The framework core and the Quad integration are intended for open-source release and
are written to be Apache-2.0-compatible, importing only from the framework core. The
`/quad/v1/capabilities` document advertises `"license": "Apache-2.0"`. Note honestly:
there is no `LICENSE` file in the repository yet. Adding it is part of the
name-and-publish step; until then the license is stated intent, not a file in the tree.
