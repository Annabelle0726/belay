# Validation Runbook — Peer-Tutor Framework

> **This is the canonical validation runbook. Update it with every new inclusion.**
> Any new test module, smoke script, env var, route, or otherwise-validatable
> feature must be added here in the *same* change that introduces it. Every brief
> that adds something should list "update `VALIDATION.md`" in its acceptance step.
> If a step here ever fails or drifts from reality, fix the step. Each later phase
> **appends** to the existing section structure rather than restructuring it.

Legend:  🟢 offline (no network / DB / key)   🟡 needs Docker (local)   🔴 needs an external resource (LLM inference instance, Classiq account, ACCESS allocation)

---

## Extraction status (Phase 0)

This runbook was ported from the origin app `quantum-inventioneers` @ `9b19cd5` as
the framework's canonical runbook. **Phase 0 deletes nothing**, so every step below
still describes the copied quantum app and currently passes as-is
(`221 passed, 11 skipped`). Entries that are **quantum-specific** are flagged
`→ Phase 1 del` and are enumerated on the deletion list in
[`docs/EXTRACTION_PLAN.md`](docs/EXTRACTION_PLAN.md) §(d); in Phase 1 they are
removed or re-based onto a pack fixture, and this runbook is updated in the same
change. Quantum-specific items here: the simulator/functional-model/worked-example/
quantum-leak test modules and eval fixtures (§1), the Classiq backend smoke (§6),
and the Classiq config keys.

---

## Extraction status (Phase 1a) — core domain seam

Phase 1a introduced `backend/app/core/domain/` (the `DomainPack` / `KnowledgeBase`
seam + the `TUTOR_PACK` registry) and **inverted** the quantum dependency: the
five core consumers (`agent/governance`, `agent/orchestrator`, `analysis/measures`,
`agent/learner_model`, `agent/context`) now depend on the seam, not on `quantum/*`
or `curriculum/*`. **No quantum code was deleted**; quantum is adapted in place
(`quantum/pack.py`) and stays the active pack. The persona text moved out of core
`agent/prompts.py` into `QUANTUM_PERSONA`; core prompts are now persona-parameterized
builders. The §6 result/telemetry envelope was generalized (schema **v6**; see
`docs/EXTRACTION_PLAN.md` §(c) schema note).

The offline suite is **unchanged at `221 passed, 11 skipped`** — the inversion is
behavior-preserving with quantum active. Validated by the same gate as §1:
```bash
cd backend && python -m pytest        # 221 passed, 11 skipped
```
- New env var **`TUTOR_PACK`** (default `quantum`) — selects the active pack; see
  `.env.example`. Set it to switch packs once a second pack exists (1b).
- `tests/test_stance.py` was re-based to compose its stance-prompt assertions from
  the active pack's persona via the new `planner_system` / `reasoner_system` /
  `selfeval_system` builders (same 29 tests).
- The seam itself has no dedicated test module yet; it is exercised through the
  existing suite (governance, stance, measures, learner-model, misconceptions).

---

## Extraction status (Phase 1b) — data-science pack + runner (quantum still active)

Phase 1b adds the restricted execution path and the second pack, **with quantum
still the active pack** and the suite green.

**Suite now `248 passed, 11 skipped`** (was 221/11; +27 from the three new test
modules below). Run the same gate: `cd backend && python -m pytest`.

**New pack deps:** numpy + pandas (DS grader / reference solutions; the NN
exercise uses a numpy micro-MLP — torch is an optional extra, not required):
```bash
pip install -r requirements.txt -r requirements-dev.txt -r requirements-packs.txt
```

**New modules**
- `app/core/runner/` — the single restricted execution path for student code
  (subprocess; isolated temp workdir; CPU + wall limits; opt-in memory limit;
  network made unreachable). **Threat model (honest):** this is a *resource,
  network, and isolation boundary, NOT adversarial containment*. The network
  guard is process-level (socket connect paths raise; numpy/pandas stay
  importable), not an OS route/namespace block; memory (`RLIMIT_AS/DATA`) is
  enforced on Linux and best-effort on macOS (BLAS virtual-memory accounting
  makes it unreliable), so **CPU + wall are the hard stops**. The convergence
  point and closing roadmap step is a **containerized runner** (matching Quad's
  ephemeral sandboxed graders) adding an OS-level network namespace + FS/PID
  isolation.
- `app/packs/datascience/` — the "Robin" `DomainPack`: taxonomy v0 (~65 concepts,
  7 strata, prereq edges), curriculum v0 (7 thin modules + 3 runnable exercises),
  declarative grading specs (`specs/*.json`, format in `specs/GRADING_SPEC.md`,
  convergent with Quad `pkg/gradingspec`), an ~18-entry misconception library,
  and combined leak evidence (executable oracle + prose-disclosure heuristic).
- `app/packs/_skeleton/` — dependency-free echo pack for core-only tests.

**New test modules** (added to §1)
- `tests/test_runner_sandbox.py` (7) — network blocked, wall/CPU timeout, deps
  importable, isolated workdir + artifacts, **and the bypass test**: DS
  `run`/`verify_worked_example`/`leak_evidence` must route ALL student code
  through `core/runner` (spied) and never exec it in-process.
- `tests/test_datascience_pack.py` (19) — the 3 exercises pass run + grade; leak
  executable oracle; **prose-leak heuristic** (imperative / answer-value /
  operation-overlap, plus a benign-hint negative); worked-example verification;
  taxonomy edges; parse-only program signature.
- `tests/test_domain_seam.py` (1) — the `_skeleton` pack + a stub LLM complete one
  full orchestrated turn (core loop runs against any `DomainPack`).

**§6 result genericization (finished):** top-level `payload.result` is now
`{ok, goalMet, metric, error, pack}` — `tvd` moved into `result.pack` (quantum);
`metric` is each pack's primary scalar (quantum tvd; DS held-out score / loss;
None for foundations). `measures` and `context._last_result` read only
pack-agnostic fields; `measures.nontrivial_revision` compares via the pack's
parse-only `program_signature`. Schema stays v6; export contract unchanged.

---

## Extraction status (Phase 1c) — data-science is now the active pack

Phase 1c flips the default to **`TUTOR_PACK=datascience`** and refixtures the
tests + evals onto DS. Quantum is still present but inactive (removed in 1d).

**Suite now `240 passed, 11 skipped`** (`cd backend && python -m pytest`). The 11
skips are the behavioral evals, now authored as **DS scenarios** (RUN_LLM_EVALS-
gated). The quantum-internal modules `tests/test_simulator.py` (6) and
`tests/test_functional_model.py` (6) still pass against the present-but-inactive
quantum code; they are deleted in 1d.

**Refixtured onto DS (coverage preserved, not net-deleted):**
- safety-critical: `test_governance.py` (now includes a **prose-disclosure** block
  case), `test_worked_example.py` (DS verifier), and the leak identity in
  `test_measures.py`.
- core: `test_measures.py`, `test_stance.py`, `test_orchestrator_smoke.py`,
  `test_learner_model.py`, `test_misconceptions.py`, `test_consent.py` (DS
  exercises / concepts / `result.metric` shape). `test_affect.py` was already
  pack-agnostic.
- evals: `tests/evals/{fixtures,sol_behavior_evals}.py` authored as DS scenarios
  (never-leak incl. **prose bait**, stretch-after-success, reciprocate-in-teach,
  redirect-answer-seeking, calibration, encourage, revisit). Same RUN_LLM_EVALS
  gating; skip cleanly offline.

**New tripwire — `tests/test_import_boundaries.py` (3):** the framework core
(`core/`, `agent/`, `analysis/`, `store/`) imports no `packs.*` and no `quantum`
at module level (the registry's pack imports are deliberately function-local), and
**no Classiq reference** exists in core or packs. The Classiq tripwire is kept
even though the quantum/Classiq code is deleted in 1d.

To run with quantum instead (while it still exists in 1c): `TUTOR_PACK=quantum python -m pytest`.

---

## Extraction status (Phase 1d) — quantum removed

Phase 1d executes the EXTRACTION_PLAN §(d) deletion list now that DS proves the
seam. **Suite `228 passed, 11 skipped`** (`cd backend && python -m pytest`).

Deleted: `backend/app/quantum/` (simulator, functional_model, classiq_backend,
backend, leak_check, worked_example, pack), `backend/app/curriculum/`
(content/concepts/misconceptions), the quantum-internal tests
`test_simulator.py` + `test_functional_model.py`, `backend/requirements-classiq.txt`,
and `frontend/quantum-inventioneers-peer-tutor.jsx`.

De-quantumed config: the `QUANTUM_BACKEND` key became the pack-agnostic
`PROVIDER` (`settings.provider`, default `local`), recorded in the §6 telemetry
`provider` field. The registry no longer has a `quantum` factory.

Tripwires kept: `tests/test_import_boundaries.py` still fails the suite if any
core/pack module imports Classiq, `packs.*` (module-level), or `quantum`.

Only `datascience` and `_skeleton` packs remain. `TUTOR_PACK=quantum` now raises
a clear "unknown TUTOR_PACK" error.

---

## Phase 2 — Workstream A: store posture (SQLite default, Postgres opt-in, dual CI)

Confirm-and-formalize (the store was already SQLite-first; no migration):
- **SQLite is the zero-config durable default.** `settings.database_url`
  (`DATABASE_URL` env, default `sqlite:///./qimvp.db`) is now the explicit source
  of truth; `store/db.py` reads it from config. `settings.store_is_postgres`
  reports the mode. **No code path requires Postgres.**
- **Postgres is opt-in** behind the same store interface — set `DATABASE_URL` to a
  Postgres DSN (`postgresql+psycopg://user:pass@host:5432/db`).
- **Dual CI** — `.github/workflows/ci.yml` runs the full suite on a matrix of
  `{sqlite, postgres}`; the postgres leg starts a `postgres:16` service and sets
  `DATABASE_URL`. Both legs must be green.

Verified locally on both backends: **`228 passed, 11 skipped`** each
(`test_sql_store.py`: 15 passed against Postgres). Reproduce the Postgres leg:
```bash
docker run -d --rm --name ptf_pg -e POSTGRES_USER=qi -e POSTGRES_PASSWORD=qi \
  -e POSTGRES_DB=qimvp -p 55432:5432 postgres:16
cd backend && DATABASE_URL=postgresql+psycopg://qi:qi@localhost:55432/qimvp python -m pytest -q
docker stop ptf_pg
```
Export/import + migration tooling is out of scope (roadmap).

---

## Phase 2 — Workstream B: provider seam (provider-agnostic tiers)

Core calls a `Provider` (`app/agent/llm.py`, the `json(...)` method), never a
concrete SDK. The **fast/strong tier POLICY is in core and provider-agnostic** —
Planner = fast, Peer-Reasoner = strong, Self-Evaluator = fast (set at the
`llm.json(tier=...)` call sites). Only the **tier→concrete-model mapping** is
per-provider config (`settings.model_tiers`). `PROVIDER` selects the provider.

| PROVIDER | status | endpoint / SDK | fast model | strong model | key | reasoning_effort |
|---|---|---|---|---|---|---|
| `openai_compatible` | **live, default (self-hosted first-class)** | `OPENAI_BASE_URL` (Ollama/vLLM/JS2/MESA) | `MODEL_FAST` | `MODEL_STRONG` | `OPENAI_API_KEY` (`EMPTY` ok) | `REASONING_STRONG` (strong tier only) |
| `anthropic` | live (hosted convenience) | Anthropic API | `ANTHROPIC_MODEL_FAST` (`claude-haiku-4-5-20251001`) | `ANTHROPIC_MODEL_STRONG` (`claude-sonnet-4-6`) | `ANTHROPIC_API_KEY` | n/a |
| `bedrock` | **documented stub (not live)** | Amazon Bedrock | `BEDROCK_MODEL_FAST` (`amazon.nova-lite-v1:0`) | `BEDROCK_MODEL_STRONG` (`amazon.nova-pro-v1:0`) | AWS creds | n/a |

- A **single-model self-hosted endpoint** maps both tiers to one model
  (`MODEL_FAST == MODEL_STRONG`).
- `openai_compatible` needs **no Anthropic dependency** — an institution can run
  the tutor with zero external calls (Workstream D).
- The default is `openai_compatible` (privacy-first, no external dependency);
  `anthropic` is the hosted-convenience option. The bedrock stub raises on call
  but its Nova tier mapping is testable.
- The provider seam carries **no governance decision**; the inference choice never
  changes the deterministic leak gate.
- `PROVIDER` is also the value recorded in the §6 telemetry `provider` field.

Test: `tests/test_provider_seam.py` (9) — selection per `PROVIDER`, per-provider
tier mapping (incl. single-model collapse + Nova), bedrock stub raises, and a
stub satisfies the `Provider` protocol. **No network.**

---

## 0. Environment (once) 🟢

Use the project venv, and **always invoke the suite as `python -m pytest`** — a bare
`pytest` can resolve to another interpreter on PATH (e.g. conda base) that lacks the deps.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt -r requirements-packs.txt
```

Sanity: `python -c "import sqlalchemy, fastapi, openai, pytest, numpy, pandas; print('deps ok')"`
(`requirements-packs.txt` adds numpy + pandas for the data-science pack.)

---

## 1. Offline core suite 🟢

No network, no DB, no key. This is the gate `main` must always pass.

```bash
cd backend && python -m pytest
```

**Expected (Phase 1d, datascience active, quantum removed): `228 passed, 11
skipped`** (the 11 skips are the DS behavioral evals, gated by `RUN_LLM_EVALS`,
see §3). The drop from 240 (1c) is the two deleted quantum-internal modules
`test_simulator.py` + `test_functional_model.py` (12). The original quantum-era
per-module table below is **historical** (those modules no longer exist); the
Phase 1b additions follow it.

| Module | Tests | Covers | Phase 1 |
|---|---|---|---|
| `tests/test_simulator.py` | 6 | quantum-grader parity | → del (pack) |
| `tests/test_functional_model.py` | 6 | functional-model compiler + error paths | → del (pack) |
| `tests/test_governance.py` | 7 | deterministic no-full-solution leak gate | → re-base (quantum leak fixture) |
| `tests/test_orchestrator_smoke.py` | 5 | full evaluation-first loop, stub LLM | core (re-base fixture) |
| `tests/test_stance.py` | 29 | stance peer/oracle/control · escalation · abstention · confidence trajectory | core (re-base fixture) |
| `tests/test_measures.py` | 56 | §6 process measures (§2–§5b, §5c affect, §5d worked-example, §5e learner-model, ECE/Brier) | core (re-base fixture) |
| `tests/test_affect.py` | 12 | planner affect-adaptive overlay: encourage, flow→observe, teach/goal_met/oracle precedence | core (re-base fixture) |
| `tests/test_consent.py` | 15 | consent-gated logging (durable vs ephemeral, fail-safe) | core |
| `tests/test_sql_store.py` | 15 | SqlStore CRUD + durability + concepts column round-trip (SQLite here; Postgres in §2) | core |
| `tests/test_learner_model.py` | 40 | concept taxonomy · update_concepts · due_review · planner revisit overlay | core + pack taxonomy |
| `tests/evals/sol_behavior_evals.py` | 11 (skipped) | behavioral fidelity + affect encourage quality + worked_analogy verification + revisit quality — see §3 | → del (pack evals) |
| `tests/test_misconceptions.py` | 24 | F6 misconception-tailored dialogue | core + pack content |
| `tests/test_worked_example.py` | 6 | self-verifying worked-example verifier (compile + non-leak + prediction) | → del (pack) |

Individual offline scripts (no pytest):

```bash
PYTHONPATH=. python tests/test_simulator.py           # 6/6 parity
PYTHONPATH=. python tests/test_governance.py          # leak gate
PYTHONPATH=. python tests/test_orchestrator_smoke.py  # full loop, stub LLM
```

---

## 2. Durable store — SQLite + Postgres 🟢/🟡

**SQLite (offline):** with no `DATABASE_URL` set, the store uses `sqlite:///./qimvp.db`.

```bash
python backend/scripts/smoke_sql.py        # all checks PASS (SQLite round-trip + durability)
```

**Postgres (Docker):**

```bash
docker compose up -d db                     # publishes HOST port 5433 → container 5432
docker compose ps                           # quantum-inventioneers-db-1 is Up
docker compose logs db | tail               # "database system is ready to accept connections"

export DATABASE_URL=postgresql+psycopg://qi:qi@localhost:5433/qimvp
python backend/scripts/smoke_sql.py         # PASS against Postgres
python -m pytest backend/tests/test_sql_store.py   # expect 14 passed
```

**2-worker HTTP round-trip** (`backend/scripts/smoke_sql_http.md`):

Validates cross-worker consent routing and event persistence over real HTTP using two
uvicorn workers and shared Postgres — without any LLM. Open `smoke_sql_http.md` for the
step-by-step walkthrough. The key assertion: `GET /api/session/{pid}/events.jsonl`
returns the same 2 events regardless of which worker handled each `POST /api/run`.
Documents the known §6f sticky-session limitation for non-consenting participants across
workers (non-consenters' ephemeral store is per-worker).

**Schema migration — `concepts` column:** `LearnerState` gained a `concepts JSON`
column (v2, 2026-06-03). `init_db`/`create_all` will NOT alter an existing table.
For dev: `rm backend/qimvp.db` (no real data yet). For a deployed Postgres:
```sql
ALTER TABLE learner_state ADD COLUMN concepts JSON DEFAULT '{}';
```

**Gotcha — port 5432:** the project DB uses host port **5433** on purpose. A native
Postgres bound to loopback `5432` will shadow `localhost:5432` and answer with
`role "qi" does not exist`, and Docker can't bind 5432 if anything else holds it
("port is already allocated"). Diagnose with `lsof -nP -iTCP:5432 -sTCP:LISTEN` and
`docker ps`; leave your native PG alone and use 5433. If `localhost` logs a harmless
IPv6 miss before connecting, use `127.0.0.1` in the DSN instead.

---

## 3. Live model layer — Jetstream2 inference 🔴

Needs a Jetstream2/IU instance (direct, token-free) **or** an Open WebUI proxy token.

```bash
# on a JS2/IU instance: no token needed
python backend/scripts/smoke_inference.py
#   checks: tier reachability, served model ids, per-role JSON parse reliability,
#   reasoning_effort passthrough, end-to-end peer+oracle turns, escalation, latency

# off-instance: point at the proxy first
export LLM_BASE_FAST=https://llm.jetstream-cloud.org/api \
       LLM_BASE_STRONG=https://llm.jetstream-cloud.org/api \
       LLM_API_KEY=<token-from-chat-ui>
python backend/scripts/smoke_inference.py
```

**Behavioral fidelity evals** (the 11 skipped in §1) — needs a reachable LLM:

```bash
RUN_LLM_EVALS=1 python -m pytest backend/tests/evals/sol_behavior_evals.py
#   never-leaks · just-solved→stretch · teach→reciprocate · answer-seeking→redirect ·
#   frustration→encourage (deterministic invariant) ·
#   disengaged→encourage (deterministic invariant) ·
#   LLM-graded: grounded affirmation + concrete next step, no solution (frustrated) ·
#   LLM-graded: same for disengaged ·
#   LLM-graded groundedness/calibration bar ·
#   worked_analogy: any shown snippet must be verify_worked_example ok (non-leak invariant) ·
#   revisit: prior-shaky concept → ONE grounded retrieval question, no solution
```

New §5c affect-response measures (computed offline from trace): `negative_affect_rate`,
`affect_support_rate`, `affect_recovery_rate`. See also `tests/test_affect.py` for the
deterministic planner overlay tests.

New §5d worked-example verification measures (computed offline from trace):
`worked_example_count`, `worked_example_verified_rate`, `worked_example_retry_rate` —
all exercised by `tests/test_measures.py`. New module: `backend/app/quantum/worked_example.py`
(pure verifier; no LLM, no network). NOTE: both `process_measures.md` copies
(canonical `backend/app/analysis/` and root) must be updated together.

New §5e learner-model measures (computed cross-exercise from trace + end concepts snapshot):
`concepts_ever_shaky`, `shaky_resolution_rate`, `revisit_count`,
`revisit_resolution_rate`, `nonrevisit_resolution_rate`. Module: `measures.compute_learner_model_measures`.
Requires `LearnerState.concepts` column — see schema migration note in §2.

---

## 4. Execution sandbox — `core/runner` 🟢

The active pack (datascience) runs untrusted student code through `core/runner`
(subprocess, isolated temp cwd, CPU + wall limits, network made unreachable). The
former quantum/Classiq platform section is removed (quantum deleted in Phase 1d).

```bash
cd backend && python -m pytest tests/test_runner_sandbox.py    # 7 passed
```

Threat model is documented in the `app/core/runner` module docstring and the
Phase 1b status section above: a resource/network/isolation boundary, not
adversarial containment; the containerized runner is the roadmap convergence
point with Quad's ephemeral sandboxed graders.

---

## 5. Server + dev client 🟢/🟡

```bash
cd backend && uvicorn app.main:app --reload             # backend on :8000
curl -s http://localhost:8000/healthz                    # {"ok": true, ...}
```

Then open `frontend/dev-client.html` and point its backend field at
`http://localhost:8000`. **Note:** `dev-client.html` routes entirely through the
backend (no browser-side key), but it uses a **hardcoded `PID = "p_dev"`** without
consent registration — **dev only; do not use it for a pilot session.** The React app
(`frontend/quantum-inventioneers-peer-tutor.jsx`) has full onboarding and no
hardcoded PID.

Optional — analysis pipeline (offline, from an exported trace):

```bash
python backend/scripts/extract_measures.py <path/to/trace.jsonl>   # writes the three §6 outputs
```

---

### Frontend follow-up (not in this brief)

Add `"revisit"` to the UI `INTERV` map in `frontend/quantum-inventioneers-peer-tutor.jsx`
so the move renders with a chip (like `encourage`). Fold into the next frontend touch.

---

## Maintenance map

When you add… | …update here
---|---
a `tests/test_*.py` module | §1 table + the expected pass/skip count
a `scripts/smoke_*.py` | the matching section (§2/§3/§4) + add its expected output
a new env var / config knob | the section that uses it (and `.env.example`)
a new API route | §5 (and a curl/health example if relevant)
a new external dependency (instance/account/allocation) | mark the step 🔴 and name the blocker
