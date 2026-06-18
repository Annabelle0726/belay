# Process Measures — Operational Definitions (§6.3 / RQ2 / H2)

*Spec v5 (2026-06-03) — longitudinal learner-model measures (§5e) added; persistent concept mastery + spaced revisit move; v4 §5c/§5d unchanged.*

Authoritative spec for Step 4 (calibration capture + trace→measure extraction).
Every measure below is a **pure, deterministic function of the ordered event trace**
(plus the grader for the leak re-check). No model calls. This file is part of the
data dictionary: a change here is a **protocol change** and must be version-stamped.

> **Before implementing:** confirm the exact run-event result keys (`goalMet`,
> `distance`) in the active pack's result envelope and `backend/app/store/models.py`,
> and recompute struggle trajectories from the ordered **run** events rather than
> assuming per-turn `attempt_signals` were persisted. Field names below reflect the
> current MVP contracts. Measures depending on `stance`, per-agent `plan.confidence`,
> and `telemetry.{escalated,abstained}` require Steps 2–3 to have landed.

---

## 0. Inputs and unit of analysis

- **Source:** the append-only JSONL trace — `run` and `turn` events — keyed to
  `(participant_id, exercise_id)`, processed in time order. Plus `learner_state`.
- **Unit:** compute per **(participant × exercise)**, then aggregate per participant.
  Condition-level comparison is downstream (§6.4 mixed-effects); this layer only
  produces the measure tables.
- **Trace fields used:**
  - run event: `result.goalMet` (bool), `result.distance` (total-variation distance, TVD), `source` (functional-model text)
  - turn event: `plan.intervention`, `plan.affective_state`, `plan.confidence` *(Step 3)*, `reasoner.confidence`, `self_eval.confidence`, `self_eval.leak_risk`, `self_eval.needs_revision`, `governance.flag`, `governance.block`, `telemetry.escalated` / `telemetry.abstained` / `telemetry.reasoning_effort` / `telemetry.confidence_trajectory` *(Step 3)*, `telemetry.worked_example` *(self-verifying examples)*, `telemetry.learner_model` *(§5e: due_review, revisit_concept, n_shaky, n_grasped, shaky_concepts)*, `stance` *(Step 2)*, `final_message`
  - §5e additionally requires the end-of-session `LearnerState.concepts` snapshot: `{concept_id: {"state","evidence","last_seen","last_review","last_review_ex"}}`. This is **not** in the event trace — it is loaded from the store after export.
- `tol = 0.07` (goal threshold, matches the grader).

## 1. Progress primitives (shared)

- `goal_met(run)  := run.result.goalMet`           (TVD ≤ tol)
- `best_distance(t) := min(run.result.distance for runs before t on this exercise)`
- `progress_run(run) := run.result.distance < best_distance(just before run)`  (strictly improves the best)
- `solved_at := first run with goal_met`
- "next run after a turn" window = the next **2** run events on the same exercise (configurable).

## 2. Solution hand-offs  — H2: *fewer* for peer vs oracle

Two levels, both deterministic:

- **`realized_handoff(turn)`** *(primary H2 contrast)* := running the code in
  `turn.final_message` through the grader yields `goal_met` for the exercise target.
  Uses the **same** check governance uses, applied to the **shown** message, so it is
  stance-agnostic. Peer ≈ 0 (the gate strips); oracle = the answer-giving turns.
- **`attempted_handoff(turn)`** := `governance.flag == "withholding_solution"` — the
  gate caught a goal-meeting snippet before it reached the student (peer-arm signal of
  latent leak pressure).
- Per participant: `realized_handoff_rate`, `attempted_handoff_rate` (counts / turns).
- **Edge:** a partial snippet that does **not** independently meet the goal (grader
  returns not-`goal_met`) is **not** a hand-off.

## 3. Redirects — preserving struggle by not just answering

- **`redirect(turn)`** := `governance.flag == "redirect_answer_seeking"` (authoritative).
- Secondary/descriptive: `plan.intervention` in a redirect-type move.
- Per participant: `redirect_rate`. If a clean answer-seeking denominator is
  unavailable, report redirects per turn and per session (do **not** invent a denominator).

## 4. Calibration — RQ2: calibrated uncertainty

Three complementary measures; report all three.

### 4a. Leak-calibration (internal, fully deterministic) — *"does Sol know when it's about to leak?"*
- `predicted_leak(turn) := self_eval.leak_risk in {"partial","full"}` (Sol flagged any leak risk). Also report the stricter `leak_risk == "full"` variant.
- `actual_leak(turn)    := governance caught/stripped a goal-meeting snippet` (`withholding_solution`)
- Build the 2×2 (predicted × actual) over turns → precision/recall of Sol's leak
  self-detection. **Headline integrity number = miss rate** (governance caught a leak
  that self-eval rated low-risk). Student-independent and tied to the governance guarantee.

### 4b. Guidance-calibration (downstream, behavioral) — *"does confidence predict helpfulness?"*
- For each **guiding** turn (`plan.intervention` not in {pure-observe}), `confidence := self_eval.confidence`.
- `outcome := the student's next run (within the window) is a progress_run or goal_met` (binary).
- Collect `(confidence, outcome)` pairs → reliability curve, **ECE** (10 bins), **Brier score**.
- **CAVEAT (state in the report):** outcome depends on the student, so this is
  calibration of confidence against *downstream progress*, not pure self-knowledge.
  Report alongside 4a.

### 4c. Abstention calibration *(Step 3)* — *"is Sol unsure on the genuinely hard items?"*
- Trigger: `telemetry.abstained == true` (or `self_eval.confidence < TAU_ABSTAIN`).
- `abstention_precision := abstained turns on items the student could not progress on (no progress in window / escalation required) / all abstained turns`
- `false_abstention_rate := abstained turns where the student did/would progress / all abstained turns`

## 5. Struggle markers — H2: *productive struggle preserved, completion not reduced*

Per (participant × exercise), recomputed from the ordered run events:

- `attempts_to_solve` := run events before `solved_at` (or total if unsolved)
- `tvd_slope` := slope of `best_distance` over successive runs (negative = converging = productive)
- `repeated_error_count` := consecutive runs sharing the same failing signature (reuse the `repeatedError` signal if persisted, else equality of error/outcome-distribution)
- `engaged_span_without_handoff` := longest run of consecutive turns/runs with no `realized_handoff`
- `nontrivial_revision_count` := successive `source` submissions whose **parsed op sequence** differs (an op added, removed, or retargeted). Use the active pack's `program_signature` (a parse-only structural fingerprint) to compare successive submissions — more robust and semantically meaningful than character edit distance (a whitespace/rename-only change is correctly ignored). Proxy for student-generated reasoning/revision.

  **Edge cases (no code change needed — these are intended behaviour):**
  (a) *Semantically-equivalent rewrite:* two submissions that differ only in whitespace, comments, or variable names but parse to the same structure are **not** counted as a revision, because `program_signature()` normalises them to the same fingerprint. This is intentional: we want to count reasoning steps, not cosmetic edits.
  (b) *Two consecutive parse-error submissions:* both fail to parse and reduce to an empty signature. The revision between them is **not** counted (the op-list diff `[]→[]` = no change). This is a known limitation: if a student writes two syntactically broken programmes in a row, the revision is invisible to this measure. Report parse-error runs separately via `result.ok == False` counts if editorial revision under error conditions is of independent interest.
- `self_directed_ratio` := student-initiated runs / (runs + Sol-prompted turns) — descriptive
- **Span classification:** `productive` = ≥2 attempts with net TVD decrease and eventual progress; `unproductive/stuck` = ≥3 attempts with no progress **and** `repeated_error`.

**Completion guardrail (report alongside so "struggle up, completion not down" is testable):**
- `solved` := any `goal_met`; `attempts_to_solve`; `turns_to_solve`.

## 5b. Escalation rate (capability-matching monitor)

Step 3's escalation lever is identical code for both arms, but it triggers on
each arm's own self-eval confidence — so **peer and oracle may escalate at
different rates**, meaning realized compute can vary with stance even though the
available capability (models, effort ceiling, policy) is matched. Defensible, but
it must be monitored:

- `escalation_rate` (per participant **and per arm**) := turns with `telemetry.escalated == true` / turns.
- Report escalation_rate by arm. If it diverges materially between peer and oracle,
  surface it and consider including realized effort (`telemetry.reasoning_effort`)
  as a covariate in the §6.4 models, so a stance effect is not confounded with
  differential compute.

## 5c. Affect-response (meta-affective support) — RQ3 / H3: *is detected affect supported, and does it recover?*

The Planner records an `affective_state` for every guiding turn; this layer reads
it back from the trace. `NEEDS_SUPPORT := {"frustration", "disengaged"}` — the
states targeted for meta-affective support.
Every measure here is a **deterministic function of the logged
`plan.affective_state` and `plan.intervention`**; turns with `plan == null`
(the control arm — no peer loop ran) carry no affect read and are **excluded**
from all of §5c.

Per (participant × exercise), over turn events with a non-null `plan`:

- `negative_affect(turn)  := plan.affective_state in NEEDS_SUPPORT`
- `negative_affect_count  := turns with negative_affect`
- `negative_affect_rate   := negative_affect_count / n_turns`
- `affect_supported(turn) := negative_affect(turn) and plan.intervention == "encourage"`
- `affect_support_count   := turns with affect_supported`
- **`affect_support_rate` := affect_support_count / negative_affect_count** — headline §5c number: of the turns where the student read as frustrated or disengaged, the fraction that received a meta-affective `encourage` move. Peer ≈ 1 (the overlay routes `NEEDS_SUPPORT → encourage`); **oracle = 0 by construction** (the answer-giver has no `encourage` move, so it is coerced to `diagnose`). This is a clean per-arm contrast, not a confound.
- **`affect_recovery_rate`** := of negative-affect turns that have a **subsequent plan_turn** on the same exercise, the fraction whose next plan_turn's `affective_state ∉ NEEDS_SUPPORT`. Negative-affect turns with no subsequent plan_turn are **excluded** from the denominator.

If `negative_affect_count == 0`, report `affect_support_rate = null` and
`affect_recovery_rate = null` (**not** 0) — there was nothing to support.

**CAVEAT:** the affect label is a model judgment and recovery depends on the
student's subsequent state — `affect_recovery_rate` is a behavioral/trajectory
measure, not pure self-knowledge. Report alongside 4b.

**Edge cases (intended behaviour, no code branch needed):**
(a) *Mixed affect:* each turn classified independently from its own `plan.affective_state`; no smoothing.
(b) *Oracle turns:* oracle turns are included in `negative_affect_count` and the recovery denominator (the planner runs), but never in `affect_support_count` — this is the intended contrast, not missing data.
(c) *No subsequent plan_turn:* excluded from `affect_recovery_rate`, counted in `negative_affect_count`.

## 5d. Worked-example verification (trustworthy scaffolding) — RQ2: *every shown worked example runs, and is never the answer.*

On a `worked_analogy` turn the reasoner emits a structured `worked_example`
(`source` + optional `expected_dist`); the orchestrator runs the deterministic
verifier (the pack's `verify_worked_example`) and records the outcome in
`telemetry.worked_example = {verified, reason, retries, shown, claim_ok}`.
Verification passes iff the example **runs** (executes without error), **does not meet
the current exercise goal** (the same `is_goal_meeting` grader §2/§4a use — so it is
genuinely a *different* problem and cannot leak the solution), and — when a
prediction was given — its simulated distribution **matches `expected_dist`** within
`tol`. The hard invariant the orchestrator enforces is `shown ⇒ verified`: an
unverified example is suppressed and replaced with a fallback line, never displayed.

Computed over turn events with a non-null `telemetry.worked_example` (i.e.,
`worked_analogy` turns that produced an example; non-worked-analogy turns and
control turns carry `null` and are excluded):

- `worked_example(turn)          := telemetry.worked_example != null`
- `worked_example_count          := turns with worked_example`
- `worked_example_verified_count := turns where telemetry.worked_example.verified == true`
- **`worked_example_verified_rate` := worked_example_verified_count / worked_example_count** — the headline §5d number: the fraction of generated examples that were verifiable on the first shown turn. Because `shown ⇒ verified`, this is **not** a measure of what students saw (they only ever see verified examples); it measures how often the reasoner produced a sound example without needing suppression.
- `worked_example_retry_rate     := mean(telemetry.worked_example.retries) over worked_example turns` — first-pass example quality (0 = verified with no regeneration).
- *Descriptive:* counts of `reason ∈ {does_not_compile, would_solve_current_exercise, prediction_mismatch}` among unverified turns.

If `worked_example_count == 0`, report `worked_example_verified_rate = null` and
`worked_example_retry_rate = null` (**not** 0) — there were no worked examples.

**Stance note:** both peer and oracle use `worked_analogy`, so §5d is computed for
both arms. The non-leak check is about the example being a *different* problem, not
about leak policy, so it applies identically to oracle — whose worked example must
still not be the current solution even though oracle may hand that solution over
through other moves.

**Edge cases (intended behaviour, no code branch needed):**
(a) *Suppressed example:* `verified == false ⇒ shown == false` — the snippet was withheld and a fallback line shown. The turn is counted in `worked_example_count` and the denominator, never in `worked_example_verified_count`. This is the safety guarantee working, not missing data.
(b) *No prediction given:* `claim_ok == null`; verification still requires compile + non-leak. Not a failure.
(c) *Non-worked-analogy and control turns:* `telemetry.worked_example == null`; excluded from every §5d measure.

## 5e. Longitudinal learner-model measures — RQ3 exploratory: *do revisited shaky concepts resolve at higher rates?*

Computed at the **participant level, cross-exercise**, from the ordered trace (§5e telemetry per turn) plus the end `LearnerState.concepts` snapshot. All rates are null when the denominator is zero (null-not-0 rule).

- `concepts_ever_shaky` := concept_ids that appeared in any turn's `telemetry.learner_model.shaky_concepts`.
- `concepts_grasped_end` := concept_ids with `state == "grasped"` in the end snapshot.
- **`shaky_resolution_rate`** := (ever_shaky ∧ grasped_end) / ever_shaky — fraction of ever-shaky concepts resolved by end.
- `revisit_count` := turns with `plan.intervention == "revisit"`.
- `distinct_concepts_revisited` := distinct concept_ids in any `telemetry.learner_model.revisit_concept`.
- **`revisit_resolution_rate`** := (revisited-while-shaky ∧ grasped_end) / revisited-while-shaky — of concepts that were shaky AND got a revisit turn, fraction resolved.
- **`nonrevisit_resolution_rate`** := (ever-shaky ∧ never-revisited ∧ grasped_end) / (ever-shaky ∧ never-revisited) — same for concepts that were shaky but never revisited.

**CAVEAT (state in report):** observational, low-N per participant, revisit only fires when relevant to the current exercise — the revisit-vs-nonrevisit contrast is exploratory/descriptive for H3, not a causal estimate. Report like §4b/§5c (alongside, with a confounding note). Do NOT claim revisit causes resolution.

**Edge cases (intended behaviour):**
(a) *Control arm:* control turns have `learner_model=null`; excluded from all §5e denominators.
(b) *Concept not in end snapshot:* treated as not grasped (conservative).
(c) *Revisit concept not shaky:* excluded from `revisited_while_shaky` — revisit_resolution_rate only applies to concepts that were shaky when revisited.

## 6. Output (what Step 4 produces)

- `measures_by_attempt.{jsonl}` — one row per `(participant_id, exercise_id)` with every field above + `stance` + `cohort` + `negative_affect_rate`, `affect_support_rate`, `affect_recovery_rate`, `worked_example_verified_rate`, `worked_example_retry_rate`.
- `measures_by_participant.csv` — per-participant aggregates (rates, means, ECE, Brier, counts) + condition + per-arm `affect_support_rate` and `affect_recovery_rate` + `worked_example_verified_rate` + `shaky_resolution_rate`, `revisit_resolution_rate`, `nonrevisit_resolution_rate`, `revisit_count`.
- `learner_model_measures.csv` — §5e participant-level rows (one row per participant, from `compute_learner_model_measures`).
- `calibration_pairs.csv` — `(participant_id, exercise_id, turn_index, confidence, outcome, leak_predicted, leak_actual, abstained)` (raw pairs for 4a–4c).
- All keyed to **anonymized** `participant_id`; no PII (per DMP).

## 7. Edge cases and rules

- Turn with no subsequent run on the exercise: excluded from **4b** (no outcome); retained for **4a**.
- Oracle / control arms: `realized_handoff` computed identically (high for oracle); `redirect`/`abstain` expected ≈ 0; **4a** and **4b** still computable. `stance` recorded so comparisons are clean.
- Unsolved exercises: `attempts_to_solve` = total; `solved=false`; included in completion stats.
- Determinism: identical input trace ⇒ identical output, byte-for-byte.