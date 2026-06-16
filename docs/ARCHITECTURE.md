# Architecture

The framework is an evaluation-first peer tutor whose safety does not depend on the
model behaving. This document describes the system as built: the per-turn loop, the
seams it depends on, the deterministic governance gate, the goals layer and its
precedence, the trace and its stable export contract, and the import boundary. Module
paths are under `backend/app/`.

## The loop

Each turn runs a fixed sequence in `agent/orchestrator.py` (`run_turn`). Stance
(`peer`, `oracle`, `control`) selects which branch runs; `control` bypasses the loop
and returns a fixed support message so condition integrity is auditable.

- Context (`agent/context.build_context`). Assembles the grounded turn context from the
  payload, the persistent learner model, and attempt signals.
- Planner (`agent/planner.plan`). Reads affect and picks exactly one pedagogical move
  (observe, co_reason, diagnose, worked_analogy, stretch, reciprocate, escalate,
  encourage, revisit, reflect). It decides; it does not write the reply.
- Peer-Reasoner (`agent/reasoner.respond`). Writes the student-facing message in the
  stance voice, reports its own confidence, and updates the running concept lists.
- Self-Evaluation (`agent/self_eval.evaluate`). Re-reads the draft against the
  stance-appropriate rubric and returns `needs_revision`, a calibrated confidence, and
  (for honored goals) a goal-alignment signal. The peer rubric refines toward not
  answering; the oracle rubric refines toward a correct answer.
- Bounded refine. While the self-eval asks for revision, the Reasoner revises, up to
  `MAX_REFINE`. Two further post-loop mechanisms follow: escalation (a capability
  lever, both stances, re-run at higher reasoning effort while under-confident, bounded
  by `MAX_ESCALATE`) and abstention (peer only, override into an honest abstention if
  still below `TAU_ABSTAIN`).
- Governance (`agent/governance.check`, then `safe_rewrite` on a block). The
  deterministic gate, run last. See below.
- Memory (`agent/memory.update`). Merges the turn's grasped/shaky into the persistent
  learner model.

The returned object is a superset of the artifact contract plus a `components` block of
telemetry the UI may ignore.

## The seams

The framework depends on interfaces, not concretions, so the same core loop runs
against any domain, provider, or store and can be exposed over a sidecar without core
knowing about it.

- Domain pack (`core/domain/pack.py`, `core/domain/registry.py`). A `DomainPack`
  supplies the curriculum, exercises, the executable `run`, `program_signature`,
  `verify_worked_example`, the misconception library, and `leak_evidence`; `knowledge`
  is optional. The registry resolves the active pack from `TUTOR_PACK` (default
  `datascience`) with lazy, function-local imports, so `core.domain` never imports a
  domain at module load. The reference pack is `packs/datascience`; `packs/_skeleton`
  is a dependency-free echo pack for core-only tests.
- Runner (`core/runner`). The single restricted execution path for untrusted student
  code. Every pack execution path (`run`, `verify_worked_example`, `leak_evidence`)
  routes code through it; nothing runs student code in the main process. Its threat
  model is stated honestly in the module docstring: a resource, network, and isolation
  boundary (subprocess, isolated temp cwd, CPU and wall limits, network made
  unreachable), not adversarial containment. CPU and wall are the hard stops; an
  OS-level containerized runner is the roadmap convergence point.
- Provider (`agent/llm.py`, config in `config.py`). Core calls a `Provider.json(...)`
  and never a concrete SDK. The fast/strong tier policy (Planner fast, Reasoner strong,
  Self-Evaluator fast) is provider-agnostic and lives in core; only the
  tier-to-model mapping is per-provider config. `PROVIDER` selects
  `openai_compatible` (default), `anthropic`, or the `bedrock` stub.
- Store (`store/repository.py`). The agent depends on the `Store` protocol
  (load/save learner state, append events, attempts, export). `InMemoryStore` is
  zero-dependency; `SqlStore` is the durable SQLAlchemy store, SQLite by default and
  Postgres opt-in behind the same interface (`DATABASE_URL`). The consent router
  (`store/consent.py`) routes durable vs ephemeral by consent.
- Quad sidecar (`integrations/quad`). A versioned `/quad/v1` HTTP/JSON surface over the
  existing loop, built from injected wiring (`build_router`) and mounted on the main
  app. It adds no prompt-level decision.

## Governance: deterministic, last, and supreme

Governance is the last step before a reply reaches the student, and it is mostly
deterministic on purpose: safety should not depend on the model behaving. Its sharpest
tool reuses the domain's own grader. The decision lives in core (`agent/governance.py`)
and consumes `LeakEvidence` supplied by the active pack: it blocks when the draft
`is_solution` (the pack ran the candidate through the executable grader against the
exercise goal) or `prose_disclosure` (the pack's prose-leak signal), and on a block it
calls `safe_rewrite` to strip the offending surface and substitute a peer-voiced
redirect. In the peer stance it also redirects a turn where the student was
answer-seeking. The oracle stance is explicitly allowed to hand over solutions.

Because governance runs last and decides post-hoc against a ground-truth oracle (the
grader plus the known solution), nothing upstream can talk it out of a block. A
worst-case reasoner that tries to leak, even with a goal demanding the answer, is
caught and the solution stripped (`tests/test_goal_safety.py::test_student_rule_cannot_leak`).

## The goals layer and its precedence

A student may set their own goals and record reflections (`agent/goals.py`); the goals
are injected into the persona-parameterized prompts (`agent/prompts.py`) as the
student's own self-set goals to honor within the stance, never as authority over it.
Precedence is fixed and is the safety claim:

1. The leak gate and the wellbeing floor bind first and are never relaxable. A goal is
   input, not authority: it can tighten or shape behavior, never loosen the gate or
   license harm. A harmful goal is recorded but marked not honored and receives decline
   framing; the honor framing is never applied to a harm-requesting goal regardless of
   the stored flag (`prompts._goals_block`).
2. The goal-alignment signal is a quality signal only, and only for honored goals. The
   self-eval scores whether the draft honors the goal within the no-solution stance; a
   poorly aligned draft drives the same refine loop. It never relaxes the floors.
3. Governance runs last and is supreme regardless of any goal.

The two floors are deliberately not symmetric, because tone has no oracle; that honest
asymmetry is the subject of `docs/PRIVACY.md` and `docs/EXTRACTION_PLAN.md` section (g).

## The trace and the export contract

Every turn appends an event via `store.make_event`. The row is a fixed eight-field
shape: `participant_id`, `ts`, `exercise_id`, `mode`, `event_type`, `stance`,
`payload`, `note`. The per-turn telemetry (component usage, governance flag, confidence
trajectory, goal-alignment, the wellbeing-softened flag, and more) rides inside
`payload`. The top-level run result is a pack-agnostic envelope
(`{ok, goalMet, metric, error, pack}`) so core reads only pack-agnostic fields and any
domain-specific scalar lives under `result.pack`.

The events model is additive and the `events.jsonl` export contract is stable. New
telemetry keys and new `event_type` values (the goals/reflection layer added
`goal_set`, `goal_alignment_check`, `reflect`, `reflection_recorded`) are added without
changing the row shape or the export, and a plain turn with no goals emits exactly one
`turn` event. Measures key on `run`/`turn` and ignore the additive types. Documenting
the contract does not change it.

## The import boundary

The framework core (`core/`, `agent/`, `analysis/`, `store/`) and the
`integrations/` sidecar import core only: no `packs.*` at module level (the registry's
pack imports are deliberately function-local) and no origin-domain code. This is a
tested tripwire (`tests/test_import_boundaries.py`), which keeps the dependency arrow
pointing from packs to core and keeps the Quad integration Apache-2.0-compatible.
