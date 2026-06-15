# Extraction Plan — Peer-Tutor Framework

Plan-of-record for extracting a domain-agnostic, evaluation-first peer-tutor
framework out of the quantum application `quantum-inventioneers`.

- **Origin:** `quantum-inventioneers` @ `9b19cd5` (see `docs/PROVENANCE.md`).
- **This is Phase 0:** copy, map, document. **No deletions, no refactors here.** The
  copied app is still the quantum app. The deletion list in §(d) and the core/pack
  split in §(a) are executed in **Phase 1**.
- All paths below are relative to the repo root unless noted; backend code lives
  under `backend/app/`.

---

## Quad / EduCloud constraint set (Phases 1–6 must honor this)

Extracted from `~/Desktop/educloud` (`project-docs/README.md`, `GOVERNANCE.md`,
`CONTRIBUTING.md`, `grants/IUSE-ESL-Level1/EduCloud-IUSE-ESL-Level1-draft.md`).

1. **Privacy — identity.** Pseudonymous only. The control plane stores Git
   usernames keyed to the **host's numeric user id**; *"Real names and SIS IDs never
   reach the server"* and it *"does not store names, SIS identifiers, or plaintext
   email"* (README). The tutor sees pseudonymous ids + submission content only.
2. **Privacy — instructor views.** *"No instructor surveillance dashboard by
   default — instructor views are class-level aggregates."* **No** *"student-vs-student
   leaderboards or ranked cohort comparisons."* (README refusals.)
3. **Privacy — grades.** *"No AI as the final word on a contested or consequential
   grade."* The tutor **never writes to grades**; tutoring is formative only
   (*"scaffolds but never grades"*, IUSE draft).
4. **License boundary.** AGPL-3.0-or-later for the **control plane** (`cmd/`,
   `internal/`); **Apache-2.0** for the interoperability primitives (`pkg/adapter`,
   `pkg/workspace`, `pkg/tutor`, `pkg/gradingspec`). *"Please don't copy
   AGPL-licensed code into the Apache-licensed `pkg/...` seams."* (CONTRIBUTING.)
   → **This framework core and its Quad integration directory must stay
   Apache-2.0-compatible and import only from the framework core**, never from any
   AGPL control plane.
5. **The four seams.** `pkg/adapter` (Git-host integrations), `pkg/workspace`,
   `pkg/tutor` (where an AI tutor plugs in), `pkg/gradingspec` (portable autograding).
   Each has plural implementations behind it.
6. **The refusals list (governance-level, not toggles).** No proctoring / keystroke
   logging / webcam monitoring; no leaderboards or ranked comparisons; no
   surveillance dashboard by default; no AI-as-final-word on grades; no required
   cloud account or mandatory hosted dependency.
7. **SQLite-first.** *"Storage is embedded SQLite by default, Postgres at scale."*
   *"Postgres is for scale, not a prerequisite."* (The origin store is already
   SQLite-first — see §(b)4 — so this is satisfied at baseline.)
8. **gradingspec.** Grading is a *"host-neutral spec run in our own sandboxed
   runners — not locked to any CI provider"*, living in the Apache-2.0 seam. The
   framework's domain "runner" (§a) should align with this concept: a pluggable,
   host-neutral grade/verify interface, not a hardcoded grader.

---

## (a) Current-tree → target-tree map (Phase 1 layout)

Target layout: `backend/app/core/{agent,domain,runner,store,measures}`,
`backend/app/packs/{datascience,_skeleton}`, `backend/app/integrations/` (empty),
`backend/app/main.py`.

| Current (origin) | Phase-1 target | Notes |
|---|---|---|
| `backend/app/agent/{orchestrator,planner,reasoner,self_eval,memory,context,llm}.py` | `core/agent/` | The domain-agnostic loop. Must be decoupled from `quantum/*` and `curriculum/*` (see §b1, §b2) behind core interfaces. |
| `backend/app/agent/prompts.py` | `core/agent/prompts.py` + pack overrides | Generic scaffolding stays in core; the **"Sol" + quantum-course stance text** (§b3) becomes pack-supplied persona/domain text. |
| `backend/app/agent/learner_model.py` | `core/agent/learner_model.py` (logic) + `core/domain` (taxonomy interface) | `update_concepts`/`due_review` are core; the concept taxonomy it imports (§b2) is pack content behind a domain interface. |
| `backend/app/quantum/{backend,simulator,functional_model,classiq_backend}.py` | **DELETED** → `packs/<domain>/runner` | The compile+execute+grade path becomes a `core/runner` interface; quantum is removed, `packs/datascience` provides a concrete runner. |
| `backend/app/quantum/{leak_check,worked_example}.py` | **DELETED** → `core/domain` interface + pack impl | The leak-oracle / "goal-met" / worked-example-verify evidence path becomes a domain-provided check (aligns with Quad `gradingspec`, §Quad-8). |
| `backend/app/curriculum/content.py` (quantum exercises) | **DELETED** → `packs/datascience`, `packs/_skeleton` | Exercise/module content is per-pack. The loader/format → `core/domain`. |
| `backend/app/curriculum/concepts.py`, `misconceptions.py` | **DELETED** → pack content behind `core/domain` | Concept taxonomy + misconception inventory are domain content. |
| `backend/app/store/{repository,models,db,consent,__init__}.py` | `core/store/` | Already domain-agnostic and SQLite-first; moves largely as-is. **§6 schema ported intact** (§c). |
| `backend/app/analysis/measures.py` + `process_measures.md` | `core/measures/` | Decouple from `quantum.leak_check`/`functional_model` (§b1) behind the domain interface. **Two `process_measures.md` copies move together** (§e7). |
| `backend/app/config.py` | `core/` config | De-quantum the config keys (Classiq, quantum_backend) → §d. |
| `backend/app/schemas.py` | `core/` HTTP schemas | De-quantum (`RunResult` bits/gates/dist/tvd/goalMet) and de-"sol" (`DialogueTurn.who`) → §b3/§d. |
| `backend/app/main.py` | `backend/app/main.py` | Routes stay; `from .quantum import ...` and quantum exercise wiring removed (§b1). |
| `backend/tests/*` | `core` tests + `packs/*/tests` | Domain-agnostic tests → core; quantum tests deleted (§d). |
| `backend/tests/evals/*` | pack evals | `fixtures.py` + `sol_behavior_evals.py` are quantum/Sol-specific → §d. |
| *(none)* | `backend/app/packs/_skeleton/` | New: template pack. |
| *(none)* | `backend/app/integrations/` | New: empty; Quad integration lands here (Apache-2.0, core-only imports). |
| `frontend/` (quantum React app) | pack/app UI (later phase) | The `quantum-inventioneers-peer-tutor.jsx` UI is domain-specific; see §e5. |

---

## (b) Migration inventory (file:line references)

### b1. Core imports of `quantum/*` (the seams to abstract in Phase 1)

| File:line | Import | Phase-1 disposition |
|---|---|---|
| `backend/app/agent/governance.py:21` | `from ..quantum.leak_check import FENCE, OP_LINE, candidate_snippets, is_goal_meeting` | Governance's leak/goal-met evidence path → `core/domain` "goal-met / leak" interface; quantum impl deleted. |
| `backend/app/agent/orchestrator.py:43` | `from ..quantum.worked_example import verify_worked_example` | Worked-example verification → domain-provided verifier interface. |
| `backend/app/analysis/measures.py:40` | `from ..quantum.leak_check import is_goal_meeting` | Same leak/goal-met interface, consumed by measures. |
| `backend/app/analysis/measures.py:94` | `from ..quantum.functional_model import synthesize` (function-local) | Measures' compile step → domain runner/synthesis interface. |
| `backend/app/main.py:35` | `from .quantum import compile_and_run, get_backend` | HTTP edge → `core/runner` selected per active pack. |

### b2. Hardcoded curriculum references in core

| File:line | Reference | Phase-1 disposition |
|---|---|---|
| `backend/app/agent/context.py:44` | `from ..curriculum.misconceptions import for_exercise` | Misconception lookup → `core/domain` interface, pack-provided. |
| `backend/app/agent/context.py:86` | `from ..curriculum.concepts import CONCEPTS` | Concept taxonomy → domain interface. |
| `backend/app/agent/learner_model.py:25` | `from ..curriculum.concepts import MISCONCEPTION_CONCEPT, concept_for_exercise, relevant_concepts` | Taxonomy helpers → domain interface; learner-model logic stays in core. |
| `backend/app/main.py:34` | `from .curriculum import curriculum, get_exercise` | Curriculum loader → `core/domain` over the active pack. |

### b3. "Sol" persona strings (de-persona / pack-supplied in Phase 1)

Core agent (counts per file): `prompts.py` (12 — incl. `SOL_STANCE` at
`prompts.py:15`, `ORACLE_STANCE` at `prompts.py:28`), `orchestrator.py` (4),
`reasoner.py` (3), `planner.py` (2), `governance.py` (2), `self_eval.py` (1).
Also: `schemas.py:11` (`DialogueTurn.who = "student" | "sol"`),
`store/models.py` + `store/consent.py` (comments), `analysis/process_measures.md`,
`curriculum/misconceptions.py`. The stance prompts also embed **"Quantum Software
Engineering course"** domain text — both the name and the domain move to pack config.

### b4. Postgres assumptions (all optional — SQLite-first already holds)

| File:line | Assumption | Note |
|---|---|---|
| `backend/app/store/db.py:12` | `DATABASE_URL` defaults to `sqlite:///./qimvp.db` | **SQLite is the default**; Postgres only when DSN is set. Satisfies Quad §7. |
| `backend/requirements.txt` | `psycopg[binary]` declared | Optional driver; keep but not required for core. |
| `backend/scripts/smoke_sql.py`, `backend/scripts/smoke_sql_http.md` | Postgres smoke walkthroughs | Infra validation; revisit in Phase 1. |
| `docker-compose.yml` (root) | Postgres service on host port 5433 | Optional scale path, not a prerequisite. |
| `backend/tests/test_sql_store.py` | Runs on SQLite by default; Postgres when DSN exported | No hard Postgres requirement. |

**Finding:** there are **no hard Postgres-required assumptions**; the store is already
SQLite-first, matching the Quad posture. No change needed in Phase 1 beyond renaming
the default DB file from `qimvp.db`.

---

## (c) §6 trace event inventory (baseline — port intact, do not alter)

**Canonical row shape** — `make_event` (`backend/app/store/repository.py:20`); SQL
table `events` (`backend/app/store/models.py:73`). Eight fields:
`participant_id, ts (ISO-8601 UTC), exercise_id, mode (study|teach),
event_type (run|turn), stance (peer|oracle|control|null), payload (JSON), note`.

**Event types emitted (exactly two):**

| `event_type` | Written at | `payload` shape |
|---|---|---|
| `run` | `backend/app/main.py:87` (POST `/api/run`); `mode="study"`, `stance=None` | `{ source, result }` — `result` is the compile/execute/grade `RunResult`. |
| `turn` (peer/oracle) | `backend/app/agent/orchestrator.py:337` | `{ event, mode, stance, source, last_result, plan, reasoner, self_eval, governance, escalated, abstained, final_message, telemetry }` |
| `turn` (control) | `backend/app/agent/orchestrator.py:110` | same keys, with `plan/reasoner/self_eval/governance = None`, `stance="control"` |

**`telemetry` block** (= the response `components`, `orchestrator.py:295–319`):
`planner, reasoner, self_eval, governance, refines, reasoning_effort, escalated,
abstained, confidence_trajectory, misconception_id, worked_example, learner_model,
timings_ms, model_tiers, quantum_backend, stance`.

**Schema/payload versions** (`backend/app/store/models.py` docstring):
- Event schema **v2** — added `stance` column (rows before it → treated as `peer`).
- Event payload **v3** — added calibrated-uncertainty fields (`reasoning_effort`,
  `escalated`, `abstained`, `confidence_trajectory`); JSON-only, no column change.
- Event payload **v5 (F6)** — added optional `telemetry.misconception_id`
  (string|null); read with `.get(..., None)`.
- LearnerState schema **v2** — added `concepts` JSON map (per-concept mastery).

**Export contract:** `GET /api/session/{pid}/events.jsonl`
(`backend/app/main.py:130`) → `durable.export_jsonl(pid)`
(`backend/app/store/repository.py:140`) → newline-delimited JSON of the eight-field
rows, **ordered by `ts`**, media type `application/x-ndjson`. Reads the **durable
store only** — non-consenting participants have no trace by design.

> This is the baseline the **additive** events in Phases 3–6 are checked against.
> Hard invariant: the event types, row shape, telemetry keys, version semantics, and
> export contract are **ported intact**. New phases may **add** fields/types; they
> may not rename or remove existing ones. The two `quantum_backend`-flavored keys
> (`telemetry.quantum_backend`, and quantum fields inside `payload.result`) are the
> only domain-specific leakage into the schema and are renamed/generalized as part of
> the §(d) de-quantum work, tracked as a schema note when it lands.

### Schema note — v6 pack-agnostic envelope (landed in Phase 1a)

The two domain-specific leaks called out above are now generalized. This is a
**structural** change to the trace, so the schema is **versioned to v6**; the
export contract (`events.jsonl`: eight-field rows, ordered by `ts`,
`application/x-ndjson`, durable-store-only) is **unchanged**.

- **`telemetry.quantum_backend` → `telemetry.provider`** (generic execution
  provider) + added **`telemetry.pack`** (the active pack id). Sets up Phase 2's
  provider telemetry. Written at `agent/orchestrator.py` (both the turn and the
  control telemetry blocks).
- **`payload.result` is now pack-agnostic at the top level** —
  `{ ok, goalMet, tvd, error, pack }` — with all domain-specific fields moved
  into a namespaced **`result.pack`** envelope (`{ id, backend, n, gates, dist,
  diff }` for quantum). Produced by `DomainPack.run` (quantum: `quantum/pack.py`)
  and surfaced over HTTP by `RunResult` (`schemas.py`). Readers that consumed the
  old top-level `dist`/`diff` (`analysis/measures._fail_sig`,
  `agent/context._last_result`) read `result.pack` first and **fall back** to the
  legacy top-level keys, so pre-v6 traces still parse.
- This stable, per-pack-invariant envelope is the AWS benchmark portability
  asset: a consumer reads the fixed top level and may inspect `result.pack`
  generically without the schema churning per domain.

**v6 finalized in Phase 1b (result genericization).** 1a left `tvd` (quantum
vocabulary) at the top level. 1b removes it: top-level `payload.result` is now
`{ok, goalMet, metric, error, pack}`. `metric` is each pack's primary scalar
(quantum tvd; DS held-out score / MLP loss; None when an exercise has none) and
is a display/telemetry slot, **not** direction-normalized across packs. `tvd`
moved into `result.pack` for quantum. `measures` (`_metric`, `_fail_sig`) and
`context._last_result` now read only pack-agnostic fields; `nontrivial_revision`
delegates to the pack's parse-only `program_signature`. Export contract unchanged.

**Phase 2 additive telemetry (no schema-version bump).** `telemetry.provider`
now carries the inference provider id (`openai_compatible`/`anthropic`/`bedrock`).
New additive `telemetry.component_usage` records per-component
`{calls, latency_ms, prompt_tokens, completion_tokens, cost}` (tokens/cost null
when the provider doesn't report them; control turns `{}`). These are **additive
keys only** — existing event types, keys, version semantics, and the
`events.jsonl` export contract are unchanged.

---

## (d) Deletion list — **EXECUTED in Phase 1d** ✅

> Phases 1b–1d are complete. 1b built `core/runner` + `packs/datascience` +
> `packs/_skeleton` with quantum still active; 1c flipped `TUTOR_PACK=datascience`
> and refixtured the suite/evals onto DS (adding `tests/test_import_boundaries.py`);
> 1d executed the deletions below. Final suite: `228 passed, 11 skipped` with
> datascience active and quantum gone. The `QUANTUM_BACKEND` config key became the
> pack-agnostic `PROVIDER`; the registry dropped its `quantum` factory; the
> import-boundary tripwire keeps Classiq/quantum/`packs.*` out of core.

1. **`backend/app/quantum/` in full:** `simulator.py`, `functional_model.py`,
   `classiq_backend.py`, `backend.py`, `leak_check.py`, `worked_example.py`,
   `__init__.py`. (Their *interfaces* — goal-met/leak check, worked-example verify,
   compile+run — are re-homed in `core/domain` + `core/runner`; the quantum
   *implementations* are deleted.)
2. **Quantum curriculum:** `backend/app/curriculum/content.py` (quantum exercises),
   `concepts.py` (quantum taxonomy), `misconceptions.py` (quantum misconceptions) —
   replaced by `packs/datascience` + `packs/_skeleton`.
3. **Quantum tests:** `test_simulator.py`, `test_functional_model.py`,
   `test_worked_example.py`, `test_governance.py` (quantum leak gate); and the
   quantum-specific portions of `test_measures.py`, `test_orchestrator_smoke.py`,
   `test_stance.py`, `test_affect.py`, `test_learner_model.py`,
   `test_misconceptions.py` (re-base onto a pack fixture).
4. **Eval fixtures:** `backend/tests/evals/fixtures.py`,
   `backend/tests/evals/sol_behavior_evals.py` (quantum + "Sol", the 11 env-gated
   skips) — replaced by pack-level evals.
5. **Classiq config keys + import paths:** `backend/requirements-classiq.txt`,
   `quantum/classiq_backend.py`, `REVERSE_BITS`, and the `quantum_backend`/Classiq
   keys in `backend/app/config.py`.
6. **"Sol" + quantum strings in core:** the `SOL_STANCE`/`ORACLE_STANCE` text and
   "Quantum Software Engineering course" domain wording in `agent/prompts.py`; the
   `"sol"` literal in `schemas.py`; quantum wording in `analysis/process_measures.md`
   (both copies) and core comments (§b3).
7. **Quantum HTTP/runner wiring:** `from .quantum import ...` in `main.py:35`; quantum
   fields in `RunResult` (`schemas.py:26`); `telemetry.quantum_backend`.
8. **Quantum frontend** (deferred, flagged in §e5): `frontend/quantum-inventioneers-peer-tutor.jsx`
   and the quantum-named client artifacts.

---

## (e) Drift — brief assumptions vs. actual repo

1. **Origin not on `main`.** Brief Step 1 expects clean+`main`. Actual: origin was on
   `chore/post-feature-dial-in`; there is no local `main`; `origin/main` (`f7ab84a`)
   is **stale** (omits the persistent-learner-model feature). **Resolution:** baseline
   taken at `9b19cd5` (trunk `feat/persistent-learner-model` + a docs-only commit),
   confirmed by the repo owner. Recorded in `PROVENANCE.md`.
2. **`main.py`/`schemas.py` location.** Brief Step 3 lists them at the backend root;
   actual: `backend/app/main.py`, `backend/app/schemas.py` (inside the `app` package).
   **Resolution:** target keeps the `app` package; `main.py` → `backend/app/main.py`.
3. **Quantum is not cleanly separable.** Brief implies a simple core/quantum split;
   actual: `quantum/*` is imported by `agent/governance`, `agent/orchestrator`,
   `analysis/measures`, and `main.py` (§b1). **Resolution:** Phase 1 introduces
   `core/domain` + `core/runner` interfaces and re-homes these seams; it is an
   abstraction, not a move.
4. **Curriculum coupling in core.** `agent/context` and `agent/learner_model` import
   the concept taxonomy / misconceptions directly (§b2). **Resolution:** a
   `core/domain` taxonomy interface; content moves to packs.
5. **A `frontend/` exists** (the quantum React app) not in the brief's target tree.
   **Resolution:** treat as domain/pack UI; its removal/replacement is deferred to a
   later phase and listed in §d8, not deleted in Phase 0 or 1's first pass.
6. **No `core/runner` or `core/domain` precedent.** The target names these dirs but
   the origin has none. **Resolution:** mapping proposed in §a (`runner` ←
   quantum compile+run path; `domain` ← curriculum loader + goal-met/leak interface).
7. **Two `process_measures.md` copies.** The repo carries `process_measures.md`
   (root) **and** `backend/app/analysis/process_measures.md`, kept byte-identical by a
   documented "both copies move together" rule (VALIDATION.md). **Resolution:** the
   pair migrates to `core/measures/` together; the invariant is preserved.
8. **`config.py` exists** (not in the brief's target). **Resolution:** → `core/`
   config; de-quantum its keys in Phase 1 (§d5).
9. **Postgres is already optional** (§b4). The brief asks to inventory
   "Postgres-required assumptions"; the finding is that **none are hard** — the store
   is SQLite-first, matching Quad §7. No drift to fix; recorded for completeness.
10. **Root `scripts/`** carries `make_clean_archive.sh` + `seed.py`; `backend/scripts/`
    carries the smoke/extract scripts. **Resolution:** `make_clean_archive.sh` is
    domain-neutral (keep); `smoke_sql*`/`smoke_inference`/`extract_measures` are
    revisited in Phase 1 alongside their subsystems.

---

## (f) Phase 1a — core domain seam (executed; quantum stays the active pack)

Phase 1a creates the `core/domain` seam and **inverts** the quantum dependency so
core components depend on interfaces, not on `quantum/*` or a concrete curriculum
module. **No quantum code is deleted**; quantum is adapted in place to implement
the seam and remains the active pack (`TUTOR_PACK`, default `quantum`). Suite
stays green (`221 passed, 11 skipped`).

**New module — `backend/app/core/domain/`:**
- `types.py` — `PersonaSpec`, `Concept`, `Taxonomy` (a `Sequence[Concept]` plus
  exercise→concept / misconception→concept / prereq edges), `Exercise`, `Module`,
  `RunResult`, `WorkedExample`, `VerifyResult`, `LeakEvidence`, `Passage`.
- `pack.py` — `DomainPack`, `KnowledgeBase`, `MisconceptionLibrary` protocols.
- `registry.py` — `get_active_pack()` / `active_pack_id()` selecting the pack from
  `TUTOR_PACK` (default `quantum`); lazy-imports the concrete pack so `core` never
  imports a domain at module load.

**`DomainPack` interface (as implemented):** `id`, `persona: PersonaSpec`,
`taxonomy: Taxonomy`, `curriculum()`, `get_exercise(id)`, `run(source, exercise)
-> RunResult`, `verify_worked_example(worked_example, exercise) -> VerifyResult`,
`misconceptions() -> MisconceptionLibrary`, `leak_evidence(draft, exercise) ->
LeakEvidence`, `knowledge() -> KnowledgeBase | None`.
- Two faithful adaptations of the brief's protocol sketch: `verify_worked_example`
  also takes the current `exercise` (the non-leak / prediction checks are defined
  relative to it), and `get_exercise` is added (the HTTP edge needs single-exercise
  lookup through the pack).

**Five consumers re-homed onto the interface** (each now obtains the active pack
via `get_active_pack()`; none import `quantum/*` or `curriculum/*`):
- `agent/governance.py` — leak gate consumes `pack.leak_evidence`; decision is core.
- `agent/orchestrator.py` — worked-example verify via `pack.verify_worked_example`;
  telemetry envelope (pack/provider).
- `analysis/measures.py` — `realized_handoff` via `pack.leak_evidence`;
  `nontrivial_revision` via `pack.run` (compiled-program comparison); no quantum import.
- `agent/learner_model.py` — taxonomy edges via `pack.taxonomy` (`update_concepts`
  / `due_review` take an optional `taxonomy`, default active pack).
- `agent/context.py` — misconceptions via `pack.misconceptions()`; concept labels +
  `due_review` via `pack.taxonomy`.
- (`agent/main.py` HTTP edge also re-homed onto the pack — curriculum / run /
  get_exercise — though it is not one of the five "core" consumers.)

**KnowledgeBase seam (declared, not built):** `search(query, k) -> [Passage]`;
`Passage` carries text + source citation + locator. Its docstring fixes the
load-bearing contract: **governance treats exercise solutions as leak-gated
regardless of whether they arrive via generation or retrieval.** No retrieval is
implemented; quantum's `knowledge()` returns `None`.

**Persona injection:** `SOL_STANCE` / `ORACLE_STANCE` and the "Quantum Software
Engineering" wording moved out of `agent/prompts.py` into `QUANTUM_PERSONA`
(`quantum/pack.py`). Core prompts are now persona-parameterized builders
(`planner_system` / `reasoner_system` / `selfeval_system`). The persona `id`
("sol") is the value formerly hardcoded in `schemas.py` (`DialogueTurn.who`),
now supplied through the seam.

### 1b gap to close — prose-leak heuristics

**Finding:** the quantum leak evidence is **executable-comparison-only**.
`quantum/leak_check.py` extracts candidate snippets (markdown fences + runs of ≥2
functional-model op lines) and runs them through the grader (`is_goal_meeting`);
there are **no domain-agnostic prose-leak heuristics** (no "the answer is …"
detector). The only generic prose heuristic in core governance is the
**answer-seeking** detector, which inspects the *student's* message, not the draft.

**Consequence for 1b:** core governance therefore has **no prose-leak heuristics**
to inherit. Running a pandas draft through the data-science grader will catch
*executable* leaks but **not a prose disclosure** of the answer (e.g. stating the
result in words, or pasting a non-executable but answer-revealing line). The 1b
data-science pack (and/or core governance) must add prose-leak heuristics —
likely surfaced as additional `LeakEvidence` signals — and the retrieval seam's
load-bearing contract above must be enforced once a `KnowledgeBase` is built.

**CLOSED in Phase 1b.** `LeakEvidence` gained an additive `prose_disclosure: bool`.
The DS pack (`packs/datascience/leak.py`) supplies it deterministically:
imperative solution-giving patterns ("the answer is", "just call…", "simply…"),
literal answer-value tokens, and essential operation-token overlap (≥2) with the
known solution — biased cautious (false positive = wasted rewrite; false negative
= leak). Core governance now blocks on `is_solution OR prose_disclosure OR`
answer-seeking; the decision stays in core, the evidence is pack-supplied.
Validated by `tests/test_datascience_pack.py` and (1c) the never-leak eval family,
which includes prose-disclosure scenarios. The `KnowledgeBase` retrieval contract
remains for whenever retrieval is built (still `knowledge() -> None`).

---

## (g) The two floors are NOT symmetric (honest claim for PRIVACY.md)

A student-set goal is honored only WITHIN two floors. Those floors are different in
KIND, and the framework does not pretend otherwise. This is the honest claim the
eventual PRIVACY.md rests on.

### The leak floor IS a post-hoc deterministic gate (it has an oracle)

Leak-detection has a ground-truth oracle: the active pack's executable grader plus
the known solution. So "did this draft leak the answer" can be decided
deterministically, AFTER the model speaks, by code that does not depend on the model
behaving. `agent/governance.check` runs `pack.leak_evidence` on the emitted draft
(`is_solution OR prose_disclosure`) and blocks/rewrites. `test_student_rule_cannot_leak`
proves it is SUPREME over a goal: even a worst-case reasoner that tries to leak, with
a "give me the full answer" goal set, is caught post-hoc and stripped. The goal is
input, never authority; it can tighten the gate, never loosen it.

### The wellbeing floor is DEFENSE-IN-DEPTH, not a single gate (no oracle)

Tone has NO ground-truth oracle. There is no grader for "is this berating" the way
there is for "does this code solve the exercise", so the wellbeing floor cannot be a
single post-hoc deterministic gate of the same strength. Its protections are layered,
and every layer except the leak-style invariants has false negatives by nature:

1. Intake detector `goals.is_harmful` (PRE-HOC, cautious). Flags self-destructive /
   berating / negative-self-talk / pressure-to-overwork goals; a flagged goal is
   recorded but `honored: false` (`floor: wellbeing`) and gets DECLINE framing, never
   honor framing. Biased cautious: a false positive routes a benign goal to a kind
   decline (acceptable); a false negative honors harm (not acceptable). It is a
   keyword/shape heuristic, so it WILL miss evasive phrasings.
2. Never-honor-framing (PRE-HOC, provable). `prompts._goals_block` gates the honor
   framing on a fresh harm re-check of the goal text, not only on the stored
   `honored` flag. So the honor framing is PROVABLY never applied to a harm-requesting
   goal regardless of the intake detector's confidence or a stale/forged flag
   (`test_honor_framing_never_applied_to_harm_requesting_goal`). This closes the
   "honored=true but harmful text" path; it does NOT close the "evade the detector
   entirely" path (same detector, no oracle).
3. Persona stance (PRE-HOC, PRIMARY). This is the primary wellbeing protection. The
   peer stance carries an explicit, non-relaxable WELLBEING FLOOR line (no berating,
   no reinforcing negative self-talk, not even on request). A capable model that
   follows its system prompt simply does not produce contemptuous tone; on frontier
   models this holds the floor on its own. It cannot, by itself, bind a deterministic
   hostile/broken model (which is why the backstop below exists).
4. Post-hoc softener `governance.soften_if_berating` (DEFENSE-IN-DEPTH, BACKSTOP). An
   OBSERVABLE heuristic backstop, not the primary protection and NOT a gate. It
   replaces an OBVIOUSLY berating/contemptuous draft with a kind redirect and caps
   confidence, and is surfaced additively at `telemetry.components.wellbeing_softened`
   so an OPERATOR can see it firing. Its value is highest on WEAK self-hosted models,
   which can produce harsh tone in a way frontier models rarely do; on a strong model
   it should almost never fire (the persona stance already holds). It is tuned for
   PRECISION on contempt: it keys on berating / contempt / negative-self-talk
   reinforcement, NEVER on bluntness or the delivery of a correction, so firm-but-kind
   honest feedback passes through unchanged
   (`test_softener_does_not_soften_firm_but_kind_correction`); softening directness
   would contradict honored goals like "be honest about my mistakes". It runs AFTER
   the supreme leak gate and never relaxes it. It has FALSE NEGATIVES by nature and is
   explicitly NOT a deterministic equivalent of the leak gate.

The hard path (a harmful goal that evades intake AND a reasoner that complies and
berates) is tested directly by
`test_adversarial_harmful_goal_evades_intake_but_tutor_does_not_berate`. Honest
finding: with a deterministic worst-case stub (the leak-side technique), the pre-hoc
prompt protections cannot bind the stub, so it is the post-hoc softener that
mechanically holds the line on the OUTPUT. That softener is real defense, but it is a
heuristic, not an oracle. The wellbeing floor is as honestly verified as a no-oracle
floor can be; it is not, and is not claimed to be, a deterministic gate.

### FLAGGED DECISION (recorded, NOT built) - distress response

Goals / reflection intake is a place a student may express GENUINE DISTRESS, not
merely a counterproductive rule (e.g. "I feel hopeless and want to give up on this
degree"). How the tutor should respond to a distress-signaling goal or reflection is
a PRODUCT and IRB decision, deliberately left to whoever owns that call. It is NOT
implemented here, and no speculative distress handling has been built. Safe defaults
recorded for the decider:

- Do NOT honor a harmful directive (the wellbeing floor already holds regardless).
- Respond BRIEFLY and KINDLY, without reinforcing or amplifying the distress.
- Do NOT diagnose; the tutor is a study partner, not a clinician.
- Leave deeper support to humans and the institution's own channels.
- Whether to surface ANY support resource is a deliberate, reviewed choice, not a
  default the framework ships on its own.

Pointer in code: `agent/goals.py` (the "FLAGGED DECISION - distress response" note
above the intake helpers).
