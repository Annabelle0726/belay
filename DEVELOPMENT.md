# Development guide — Quantum Inventioneers (Sol peer-tutor)

This repo is set up to be driven from **VS Code + Claude Code**. The notes below
get a new machine from clone to a passing test suite, then to a running server.

## 0. Prerequisites

- Python 3.11+ and `pip`
- Node 18+ (only if you build the React front-end; the dev client needs nothing)
- Git
- VS Code, with the **Claude Code** extension installed
- Optional: a Classiq account (only for the real quantum backend)

## 1. Clone and create an environment

```bash
git clone <this-repo-url> quantum-inventioneers
cd quantum-inventioneers/backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt -r requirements-dev.txt
```

## 2. Run the offline tests first (no network, no key)

These three prove the core is healthy without any model or cloud access:

```bash
cd backend
PYTHONPATH=. python tests/test_simulator.py          # quantum-grader parity (6/6)
PYTHONPATH=. python tests/test_governance.py          # the no-solution-leak gate
PYTHONPATH=. python tests/test_orchestrator_smoke.py  # full loop with a stub LLM
# or the whole suite (LLM evals auto-skip without RUN_LLM_EVALS):
python -m pytest          # use `python -m` so it runs in THIS venv, not a stray
                          # `pytest` on PATH (e.g. conda base) that lacks the deps
```

## 3. Configure the model layer

```bash
cd ..                 # repo root
cp .env.example .env
```

The defaults target the **Jetstream2 Inference Service** (gpt-oss-120b + Llama 4
Scout). Two modes:

- **On a Jetstream2 / IU instance** — no token needed; the direct endpoints in
  `.env.example` work as-is.
- **Off-instance dev** — point `LLM_BASE_FAST` and `LLM_BASE_STRONG` at the Open
  WebUI proxy (`https://llm.jetstream-cloud.org/api`) and set `LLM_API_KEY` to a
  token from the chat UI. For a ceiling comparison you can instead set
  `LLM_PROVIDER=anthropic` with an `ANTHROPIC_API_KEY`.

`.env` is git-ignored — never commit a real token.

## 4. Run the server + dev client

```bash
cd backend && uvicorn app.main:app --reload          # backend on :8000
# then open ../frontend/dev-client.html and point its backend field at
# http://localhost:8000
```

Health check: `GET http://localhost:8000/healthz`.

## 5. Working with Claude Code in this repo

Suggested division of labor when continuing development:

- **Agentic loop** (`backend/app/agent/`): planner · reasoner · self_eval ·
  governance · memory · orchestrator. Each component has one job and a strict
  JSON contract; keep changes inside a single component and re-run
  `tests/test_orchestrator_smoke.py`.
- **Quantum layer** (`backend/app/quantum/`): functional-model compiler, local
  simulator, Classiq backend, grader. `tests/test_simulator.py` is the parity
  oracle — keep it green.
- **Governance is safety-critical** (`backend/app/agent/governance.py`): the
  no-full-solution guarantee is enforced here deterministically, not by the
  model. Any change must keep `tests/test_governance.py` passing.
- **Research trace** (`backend/app/store/`): the append-only event log is the
  study dataset. Treat schema changes as protocol changes (see `DATA_AND_IRB.md`).

### Open work items (from the handoff)

1. **[CODE DONE — live run pending]** Live JS2 inference smoke test.
   `backend/scripts/smoke_inference.py` is written and committed (tagged v0.1.0-pilot).
   Requires a Jetstream2/IU instance or an Open WebUI proxy token to run.
2. **[PENDING]** Confirm the ACCESS allocation (Education type) + credit amount with the
   UArizona ACCESS Resource Provider / Campus Champion. No allocation has been
   requested yet.
3. **[DONE]** Frontend rewire — `run()` → `/api/run`, `askSol()` → `/api/sol/turn`.
   Applied in `frontend/quantum-inventioneers-peer-tutor.jsx`. The in-browser
   Anthropic key and direct `api.anthropic.com` call have been removed. Consent
   onboarding and the `BACKEND`/`OFFLINE` flags are live.
4. **[DONE]** Pilot hardening:
   - **IRB consent-gate** — `ConsentRouter` in `backend/app/store/consent.py`;
     `test_consent.py` (15 tests); durable Participant rows for all, ephemeral
     store for non-consenters. Live on `main`.
   - **Postgres** — `psycopg[binary]>=3.1` declared; `docker-compose.yml` Postgres
     service enabled; `test_sql_store.py` (14 tests, runs on sqlite or postgres);
     `smoke_sql.py` written. **[CODE DONE — live DB run pending]**
5. **[PENDING]** Classiq backend — authenticate once and run the Bell-pair endianness
   smoke test (flip `REVERSE_BITS` if `01`/`10` appear where `00`/`11` are expected).
   Requires a Classiq account + `classiq.authenticate()`.

## 6. Branch / commit conventions

- `main` stays releasable (offline tests green).
- Feature branches: `feat/<area>-<short-desc>`, e.g. `feat/frontend-backend-rewire`.
- Never commit `.env`, `*.db`, or any `*.jsonl` export of the research trace.
- **Update `VALIDATION.md` with every new inclusion** — any new test module, smoke
  script, env var, or validatable feature is added to the runbook in the same change.

## 7. Transfer / archival

To hand the repo off as a clean, secret-free artifact, use
`scripts/make_clean_archive.sh`. It refuses to run with a dirty working tree
(commit first) and writes to the **parent** directory, so the output never lands
inside the repo. Both modes carry only tracked content — no `.env`, `*.db`, or
`*.jsonl` trace export ever ends up in the archive.

```bash
scripts/make_clean_archive.sh           # zip   (default): tracked files at HEAD
scripts/make_clean_archive.sh zip       #   → ../quantum-inventioneers-sol.zip
scripts/make_clean_archive.sh bundle    # bundle: full history, all refs
#   → ../quantum-inventioneers-sol.bundle  (clone with: git clone <bundle> quantum-inventioneers)
```

- **zip** (`git archive`) — a flat snapshot of the tree at `HEAD`; smallest, no
  git history. Best for sharing the code as-is.
- **bundle** (`git bundle --all`) — the whole repository (every branch + history)
  in one file you can `git clone` from. Best for a faithful repo transfer.

---

See `VALIDATION.md` for the full validation runbook (offline tests, Postgres,
live model layer, Classiq), `README.md` for the architecture overview,
`ARCHITECTURE.md` for the loop diagram and component contracts, `DEPLOY_ACCESS.md`
for Jetstream2/ACCESS deployment, and `DATA_AND_IRB.md` for the event schema and
human-subjects framing.
