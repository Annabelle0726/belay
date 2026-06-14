# Quantum Inventioneers — Repo Status Report

Generated: 2026-06-10 · Branch: `feat/persistent-learner-model` (integration trunk;
this report was stamped from `chore/post-feature-dial-in`, a docs-only branch off it)

> Source of truth is the code + a real `pytest` run. The detailed feature-status
> narrative further down was cross-checked against the tree on the date above.

---

## 1. Runtime Evidence

### 1.1 Git State

`feat/persistent-learner-model` is the integration trunk (origin/HEAD, default PR
base). All shipped work has been merged into it; the old per-feature branches were
pruned (see `chore(repo): prune merged feature branches`).

**`git log --oneline -12`**

```
f53441b feat(agent): persistent learner model + spaced follow-up (revisit)
f7ab84a merge: unite affect-adaptive (§5c) and self-verifying worked examples (§5d)
8ba5052 feat(agent): affect-adaptive meta-affective support
40621d0 feat(agent): self-verifying worked examples
9278eb7 chore(repo): prune merged feature branches; salvage HTTP SQL smoke
62708be docs(dev): add VALIDATION runbook; declare test deps; fix setup steps
35a8652 fix(compose): publish Postgres on host 5433 to avoid native PG on 5432
cf59e85 docs: reconcile DEVELOPMENT/README with shipped state; address dev-client key
e262d62 docs(store): salvage 2-worker HTTP smoke walkthrough from feat/sql-smoke
6690e6a merge: Sol peer-tutor V1
796e1ea feat(curriculum): integrate F6 misconception-tailored dialogue into the main chain
d3f2859 docs(status): generate repo status + feature matrix
```

### 1.2 Test Results

```
Command : cd backend && python -m pytest
Result  : 221 passed, 11 skipped
```

Per-module (offline core suite — no network / DB / key):

| Module | Tests | Covers |
|---|---|---|
| `tests/test_simulator.py` | 6 | quantum-grader parity |
| `tests/test_functional_model.py` | 6 | functional-model compiler + error paths |
| `tests/test_governance.py` | 7 | deterministic no-full-solution leak gate |
| `tests/test_orchestrator_smoke.py` | 5 | full evaluation-first loop, stub LLM |
| `tests/test_stance.py` | 29 | stance peer/oracle/control · escalation · abstention · confidence trajectory |
| `tests/test_measures.py` | 56 | §6 process measures (§2–§5b, §5c affect, §5d worked-example, §5e learner-model, ECE/Brier) |
| `tests/test_affect.py` | 12 | planner affect-adaptive overlay (§5c encourage) |
| `tests/test_consent.py` | 15 | consent-gated logging (durable vs ephemeral, fail-safe) |
| `tests/test_sql_store.py` | 15 | SqlStore CRUD + durability + `concepts` column round-trip |
| `tests/test_learner_model.py` | 40 | concept taxonomy · update_concepts · due_review · planner revisit overlay (§5e) |
| `tests/test_misconceptions.py` | 24 | F6 misconception-tailored dialogue |
| `tests/test_worked_example.py` | 6 | self-verifying worked-example verifier (§5d) |
| `tests/evals/sol_behavior_evals.py` | 11 (skipped) | behavioral fidelity — gated by `RUN_LLM_EVALS`, needs a reachable LLM (§3 of VALIDATION.md) |

The 11 skips are the LLM behavioral evals (never-leak, stretch-after-solve,
teach→reciprocate, answer-seeking→redirect, frustration/disengaged→encourage,
worked_analogy non-leak, revisit retrieval-question). They run only with
`RUN_LLM_EVALS=1` and a reachable Jetstream2/Anthropic endpoint.

---

## 2. Feature Status Matrix

### A. Agentic Core (five-component evaluation-first loop)

| Feature | Status | Files |
|---------|--------|-------|
| **Planner** (affect read + ONE intervention, deterministic `_rules_overlay`) | **DONE** | `agent/planner.py`, `agent/prompts.py` |
| **Peer-Reasoner** (peer voice + self-reported confidence) | **DONE** | `agent/reasoner.py`, `agent/prompts.py` |
| **Self-Evaluation** (calibrated confidence, rubric critique, needs_revision) | **DONE** | `agent/self_eval.py` |
| **Governance** (deterministic no-full-solution gate, redirect, escalate) | **DONE** | `agent/governance.py`, `quantum/leak_check.py` |
| **Memory** (grasped/shaky + structured per-concept mastery map) | **DONE** | `agent/memory.py`, `agent/learner_model.py`, `store/repository.py` |

### B. Pedagogy / IUSE Constructs

| Feature | Status | Files | Tests |
|---------|--------|-------|-------|
| **Stance peer/oracle/control** (RQ2/H2 manipulated variable) | **DONE** | `agent/orchestrator.py`, `schemas.py` | `test_stance.py` |
| **Calibrated confidence + confidence_trajectory** | **DONE** | `agent/{planner,reasoner,self_eval,orchestrator}.py` | `test_stance.py` |
| **Uncertainty-driven escalation** (`reasoning_effort` lever, both arms) | **DONE** | `agent/orchestrator.py`, `agent/llm.py` | `test_stance.py` |
| **Peer-only abstention** (below `TAU_ABSTAIN`) | **DONE** | `agent/orchestrator.py` | `test_stance.py` |
| **Teach / role-reversal mode** (protégé effect) | **DONE** | `agent/prompts.py` (`TEACH_ADDENDUM`) | `test_stance.py` |
| **Misconception-tailored dialogue (F6)** | **DONE** (merged) | `curriculum/misconceptions.py`, `agent/context.py` | `test_misconceptions.py` (24) |
| **Affect-adaptive meta-affective support (§5c)** — frustration/disengaged → `encourage` | **DONE** | `agent/planner.py` overlay, `agent/prompts.py` | `test_affect.py` (12) |
| **Self-verifying worked examples (§5d)** — shown snippet compiled + non-leak checked | **DONE** | `quantum/worked_example.py`, `agent/reasoner.py` | `test_worked_example.py` (6) |
| **Persistent learner model + spaced follow-up (§5e)** — structured concept map drives `revisit` | **DONE** | `agent/learner_model.py`, `agent/memory.py`, `curriculum/concepts.py`, `store/models.py` (`concepts` column) | `test_learner_model.py` (40) |

### C. Infra / Data / CI

| Feature | Status | Files | Notes |
|---------|--------|-------|-------|
| **JS2 inference layer** (gpt-oss-120b + llama-4-scout) | **DONE** (code); unverified on live JS2 | `agent/llm.py`, `scripts/smoke_inference.py` | per-tier base URLs; `reasoning_effort` passthrough; smoke script ready |
| **Quantum local simulator** | **DONE** | `quantum/simulator.py`, `quantum/backend.py` | exact state-vector; offline/CI |
| **Classiq backend seam** | **STUBBED** | `quantum/classiq_backend.py` | compiles to Qmod; `REVERSE_BITS` endianness smoke not run (needs account) |
| **Curriculum** (concept taxonomy + exercises) | **DONE** | `curriculum/concepts.py`, `curriculum/content.py` | `CONCEPTS` map backs §5e revisit labels |
| **§6 trace + export route** | **DONE** | `store/`, `main.py` (`GET /api/session/{pid}/events.jsonl`) | append-only; stance column |
| **§6 measures extraction** | **DONE** | `analysis/measures.py`, `analysis/process_measures.md` | §2–§5e incl. ECE + Brier; `test_measures.py` (56) |
| **Consent-gating (ConsentRouter)** | **DONE** | `store/consent.py`, `main.py` | durable vs ephemeral; fail-safe |
| **Durable SqlStore** (SQLite → Postgres) | **DONE** | `store/{db,models,repository}.py` | `concepts JSON` column (v2); `test_sql_store.py` (15) |
| **Frontend wired to backend** | **DONE** | `frontend/quantum-inventioneers-peer-tutor.jsx`, `frontend/api-client.js` | glass box renders §5c/§5d/§5e telemetry; no model key in browser |

### D. Blocked on external resources (pilot-readiness)

| Item | Blocked on |
|------|-----------|
| Live JS2 inference smoke (`scripts/smoke_inference.py`, ready) | A Jetstream2 / IU instance or Open WebUI proxy token |
| `RUN_LLM_EVALS` behavioral evals (the 11 skipped) | Same JS2 instance or a configured LLM provider |
| Postgres live validation (`scripts/smoke_sql.py`, ready) | `docker compose up -d db` (publishes host **5433**) or any `postgresql+psycopg://` DSN |
| Classiq backend endianness smoke | A Classiq account + `classiq.authenticate()` |
| ACCESS allocation | NSF ACCESS Education allocation request (see `DEPLOY_ACCESS.md`) |

---

*Generated by reading source, running `pytest` (221 passed / 11 skipped), and
examining git history. Code was the source of truth; docs were cross-checked.*
