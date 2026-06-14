# Architecture

## The evaluation-first peer loop

Every Sol turn runs this sequence (`backend/app/agent/orchestrator.py`). It is
the agentic-architecture draft's modular design made real and *sequential*,
instead of one prompt emitting all five fields at once.

```
            request (event, exercise, source, last result, recent dialogue, mode)
                                   │
                         build grounded context  ─────────────┐  (agent/context.py)
                                   │                            │  + persistent learner model
                                   ▼                            │  + attempt signals (store)
                    ┌───────────────────────────┐
                    │  PLANNER        (fast tier) │  affect read + ONE intervention
                    │  + rules overlay            │  (teach→reciprocate; solved→stretch;
                    │                             │   repeated-error→diagnose;
                    │                             │   neg-affect→encourage; due/shaky→revisit)
                    └───────────────────────────┘
                                   │  plan
                                   ▼
                    ┌───────────────────────────┐
                    │  PEER-REASONER (strong tier)│  Sol's message in peer voice
                    └───────────────────────────┘  + self-reported confidence
                                   │  draft
                                   ▼
                    ┌───────────────────────────┐
                    │  SELF-EVALUATION (fast tier)│  rubric critique + calibrated confidence
                    └───────────────────────────┘  + needs_revision?
                          │ yes (≤ MAX_REFINE)        │ no
                          └──────► re-reason ◄────────┘
                                   │  best draft
                                   ▼
                    ┌───────────────────────────┐
                    │  GOVERNANCE   (deterministic)│  run Sol's code through the grader;
                    └───────────────────────────┘  strip any full solution; flag escalate/redirect
                                   │  gated draft
                                   ▼
                    ┌───────────────────────────┐
                    │  MEMORY                     │  merge grasped/shaky into learner model
                    └───────────────────────────┘
                                   │
                    emit artifact-compatible contract  +  append §6 trace event
```

## Component contracts

All components share one peer **stance** (`agent/prompts.py::SOL_STANCE`) so Sol
is one coherent character; each has a single job and a strict JSON output.

- **Planner** — in: context. out: `affective_state, affect_reasoning,
  intervention, target_concept, planner_note` (+ `revisit_concept` when revisiting).
  A deterministic `_rules_overlay` enforces invariants that must never be left to
  the model: teach→`reciprocate`, just-solved→`stretch`, repeated-error→`diagnose`,
  negative affect (frustration/disengaged)→`encourage` (§5c meta-affective), and a
  due/shaky prior concept→`revisit` (§5e spaced follow-up). The full intervention
  set: `observe, co_reason, diagnose, worked_analogy, stretch, reciprocate,
  encourage, revisit, escalate`.
- **Peer-Reasoner** — in: context + plan (+ optional critique). out: `message,
  check_question, confidence, grasped, shaky`. Honors the HARD RULE (no full
  solution) and revises when given a critique. A `worked_analogy` turn may carry a
  **self-verifying worked example** (§5d): any code snippet it shows is compiled and
  checked for non-leak by `quantum/worked_example.py` before it reaches the student;
  an unverified snippet is suppressed (`verified=false ⇒ shown=false`).
- **Self-Evaluation** — in: exercise + student state + draft. out:
  `needs_revision, confidence, leak_risk, self_critique, reasons`. Rubric:
  no-leak · grounded · calibrated · preserves-struggle · peer-voice. Its
  `confidence` is the calibrated number the glass box displays.
- **Governance** — deterministic. Extracts code (fenced blocks + bare op-runs)
  and runs each through `quantum.compile_and_run` against the exercise target;
  any `goalMet` snippet is a leak → strip + flag `withholding_solution`. Also
  detects answer-seeking (→ `redirect_answer_seeking`) and escalation. Returns
  `{flag, block, reasons}`; `safe_rewrite` removes solution code, keeps the peer
  prose, and caps confidence.
- **Memory** — merges the turn's grasped/shaky into the persistent learner model
  (grasped wins over shaky) **and** updates a structured per-concept mastery map
  (`LearnerState.concepts`: `{concept_id: {state, evidence, last_review, …}}`,
  persisted across sessions). This map drives the §5e `revisit` overlay and the
  longitudinal measures; the orchestrator additionally appends a full trace event.

## Resource-aware model tiers (Jetstream2 Inference Service)

The "resource-aware orchestration" idea is realized with the **Jetstream2
Inference Service** — OpenAI-compatible, US-origin, open-weight models hosted at
Indiana University. `agent/llm.py::OpenAICompatLLM` is the default client.

- **fast** (`MODEL_FAST`, default **Llama 4 Scout**) — Planner + Self-Evaluator:
  frequent, structured, low-latency calls.
- **strong** (`MODEL_STRONG`, default **gpt-oss-120b**, `REASONING_STRONG=high`)
  — Peer-Reasoner: reasoning + voice. gpt-oss-120b exposes configurable
  reasoning effort (low/medium/high), passed through as `reasoning_effort`.

Each tier carries its own base URL because the JS2 direct endpoints are
per-model. Two access modes:

- **On a Jetstream2 / IU instance** (production): hit the direct vLLM/SGLang
  endpoints (`.../gpt-oss-120b/v1`, `.../llama-4-scout/v1`) with **no token**;
  access is restricted to JS2/IU networks. No commercial key, no per-token cost,
  and the service consumes **no Jetstream2 SUs**.
- **Off-instance** (dev): point both base URLs at the Open WebUI proxy
  (`https://llm.jetstream-cloud.org/api`) and set `LLM_API_KEY` to a token from
  the chat UI, or tunnel to the direct endpoints.

Data stays within IU's data center and is not used for training — which is also
why this is the right answer for the §6 / IRB data-handling story. The model
choice is deliberately swappable (`config.py`); the architecture is
model-agnostic, and `LLM_PROVIDER=anthropic` remains available for off-JS2
development or ceiling comparisons.

## Output contract (why the UI is unchanged)

The orchestrator returns exactly the artifact's Sol contract
(`affective_state, affect_reasoning, confidence, intervention, planner_note,
self_critique, governance, memory{grasped,shaky}, message, check_question`) plus
a `components` block (`planner, reasoner, self_eval, governance, refines,
reasoning_effort, escalated, abstained, confidence_trajectory, misconception_id,
worked_example, learner_model, timings_ms, model_tiers, quantum_backend`). The
artifact ignores unknown fields, so it renders backend output as-is; the richer
telemetry is available when you want to surface it. `learner_model` (§5e:
`n_grasped, n_shaky, revisit_concept, shaky_concepts, due_review`) and
`worked_example` (§5d) are **null on the control arm**, which runs no peer loop.

## Quantum backends & endianness

`QuantumBackend` (`quantum/backend.py`) returns an outcome-probability dict keyed
by bitstring (qubit 0 = leftmost), so the grader and tutor context are
backend-agnostic.

- **LocalSimulator** — exact state-vector probabilities; no deps; offline/CI.
- **ClassiqBackend** — lowers the gate list to a Qmod `main`, `synthesize()`s,
  and executes via `ExecutionSession`, folding sampled counts into probabilities.
  Classiq's reported bit order may be reversed relative to our convention;
  `REVERSE_BITS` reconciles it. **Confirm with a Bell-pair smoke test (03 ·
  Entanglement) the first time you wire a live backend** — if `01`/`10` appear
  where `00`/`11` are expected, flip the flag.
