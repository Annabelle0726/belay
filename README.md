# Quantum Inventioneers — Peer-Tutor MVP

A working backend + front-end for **Sol**, a peer-learner AI for an
undergraduate Quantum Software Engineering course. Sol is deliberately *not* an
expert/oracle tutor: it is a classmate a few weeks ahead that co-reasons, shows
**calibrated uncertainty**, **preserves productive struggle**, abstains/escalates
when unsure, and **flips roles** so the student teaches it.

This repo turns the validated single-file artifact into a system you can pilot.

## What this closes (vs. the artifact)

| | Artifact (demo) | This MVP (system) |
|---|---|---|
| Quantum execution | in-browser stand-in simulator | `QuantumBackend` seam: local simulator **or** real **Classiq** synthesis + execution |
| The tutor | one in-browser prompt emitting every field at once | server-side, **five separated components** with a real evaluation-first loop |
| Memory / data | browser-only session log | persistent learner model + **append-only research trace** (the §6 dataset) |
| Model layer | model key in the browser | **Jetstream2 Inference Service** — US-origin open-weight models (gpt-oss-120b, Llama 4 Scout), no commercial key, no per-token cost |

The backend keeps the artifact's two contracts (the `run()` result shape and
Sol's JSON turn shape), so the existing UI renders backend output unchanged.

## Quickstart (offline, no Classiq, no key needed for the core tests)

```bash
cd backend
python -m pip install -r requirements.txt          # for the HTTP server
PYTHONPATH=. python tests/test_simulator.py         # quantum parity (no deps)
PYTHONPATH=. python tests/test_governance.py         # safety gate   (no deps)
PYTHONPATH=. python tests/test_orchestrator_smoke.py # full loop, stub LLM (no deps)
```

Run the server. The model layer defaults to the **Jetstream2 Inference Service**
(OpenAI-compatible). On a Jetstream2 / IU instance it needs no token; for
off-instance dev, point `LLM_BASE_*` at the Open WebUI proxy and set a token:

```bash
cd backend && uvicorn app.main:app --reload
# on a JS2 instance: nothing else needed (gpt-oss-120b + Llama 4 Scout, no key)
# off-instance dev: export LLM_BASE_FAST=https://llm.jetstream-cloud.org/api \
#                          LLM_BASE_STRONG=https://llm.jetstream-cloud.org/api \
#                          LLM_API_KEY=<token from the chat UI>
# then open ../frontend/dev-client.html and point it at http://localhost:8000
```

Switch the quantum engine to the real platform with `QUANTUM_BACKEND=classiq`
(after `pip install -r requirements-classiq.txt` and `classiq.authenticate()`).
See `frontend/README.md` to wire the rich artifact to the backend.

## The architecture, and how it maps to the proposals

One system, two readings: the **agentic-architecture** draft describes the
engine; the **NSF** proposal describes the peer-tutor application and its
research instrument. Each component below is real code (`backend/app/agent/`).

| Agentic component | Module | Serves NSF (§6) |
|---|---|---|
| Planner | `agent/planner.py` | chooses the pedagogical move — the **manipulated variable** |
| Execution / Reasoner | `agent/reasoner.py` + `quantum/` | the tutoring "treatment"; Classiq + ACCESS execution surface |
| Self-Evaluation | `agent/self_eval.py` | calibrated uncertainty + **preserve-struggle** check (RQ2); drives refine/abstain |
| Governance | `agent/governance.py` | enforces "no full solution" via the grader itself; logs redirects/escalations |
| Persistent Memory | `agent/memory.py` + `store/` | longitudinal learner model — the signal for **H3** + the analysis dataset |
| Resource-aware tiers (now Jetstream2 inference) | `config.py` — gpt-oss-120b (strong) / Llama 4 Scout (fast) | no per-token cost, no SUs; sovereign US-hosted models for a cohort at scale |
| Affect / cognitive-state signals | first-class inputs in `agent/context.py` | the meta-affective support strategy |

See `ARCHITECTURE.md` for the loop diagram and per-component contracts,
`DEPLOY_ACCESS.md` for Jetstream2/ACCESS deployment (the proposal's CI
commitment), and `DATA_AND_IRB.md` for the event schema and anonymization.

## Testing & evals

- `tests/test_simulator.py` — the artifact's validated 6-case physics suite, now grading on the backend.
- `tests/test_functional_model.py` — the functional-model compiler + error paths.
- `tests/test_governance.py` — the solution-leak gate (the safety-critical piece).
- `tests/test_orchestrator_smoke.py` — the full loop with a stub LLM (no network).
- `tests/evals/sol_behavior_evals.py` — **behavioral** evals on real model output: never leaks, just-solved→stretch, teach→reciprocate, answer-seeking→redirect, plus an LLM-graded groundedness/calibration bar. Skips without `ANTHROPIC_API_KEY`.

```bash
cd backend && pytest            # core suite (evals auto-skip without a key)
```

## Layout

```
backend/app/
  quantum/      functional-model compiler, local simulator, Classiq backend, grader
  agent/        planner · reasoner · self_eval · governance · memory · orchestrator · prompts
  store/        SQLAlchemy models, repository (SqlStore + InMemoryStore), §6 trace
  curriculum/   three stackable modules + exercises
  main.py       FastAPI routes
frontend/       the rich artifact + a zero-dep dev client + api-client.js
```
