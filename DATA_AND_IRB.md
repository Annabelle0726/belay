# Data & IRB

The system is instrumented as a research apparatus from the start: every run and
every tutor turn is written to an **append-only** event log that is the §6 data
stream. This document is the reference for the human-subjects framing.

## What is stored (and what is not)

By design there is **no PII**. A participant row is an opaque id plus an
anonymized code and a consent flag:

```
participants(id, anon_code, consent, created_at)
```

Concept-level learner state (Sol's persistent model of the student):

```
learner_state(participant_id, grasped[], shaky[], attempts, updated_at)
```

The trace — never updated, only inserted:

```
events(id, participant_id, ts, exercise_id, mode, event_type, payload, note)
  event_type = "run"  -> payload: { source, result }
  event_type = "turn" -> payload: { event, mode, source, last_result,
                                     plan, reasoner{message,confidence,grasped,shaky},
                                     self_eval{needs_revision,confidence,leak_risk,...},
                                     governance{flag,block,reasons},
                                     final_message, telemetry{timings_ms, model_tiers, ...} }
```

Source code the student writes is functional-model text (not free-form personal
data), but it is still treated as participant data under the protocol.

## Consent & anonymization

- `POST /api/participant` records `{anon_code, consent}` and returns the opaque
  `participant_id` used for the session. Enrolment maps real identities to
  `anon_code` **outside** this system (a separately held key), per the IRB plan.
- Run/turn logging should be gated on `consent = true` in the deployment policy;
  un-consented use can run against `InMemoryStore` (ephemeral, nothing persists).

## Retention & export

- The database **is** the dataset; back it up and retain per the approved
  protocol.
- Export for analysis: `GET /api/session/{participant_id}/events.jsonl` (one JSON
  object per line), or `Store.export_jsonl()` for a full pull. JSONL drops
  straight into pandas/R.

## How the trace answers the research questions

- **RQ2 — peer-tutor effect vs. Classiq's current support.** `mode`,
  `intervention`, the `governance` flags (especially `withholding_solution` /
  `redirect_answer_seeking`), and the `self_eval` calibration fields let you
  quantify *how* Sol intervened and whether it preserved struggle, per turn and
  per condition.
- **H3 — larger benefit for lower-prior-experience students.** `learner_state`
  trajectories (grasped/shaky over time) plus per-exercise `attempts` give the
  longitudinal signal to test the interaction with prior experience.
- Run-level grading (`result.goalMet`, `result.tvd`) over the `run` events gives
  the learning-progress outcome to attach those analyses to.

## Caveat

The behavioral guarantees the trace records (e.g. "no full solution leaked") are
enforced deterministically by the Governance component (`agent/governance.py`),
not merely requested of the model — so the logged `governance` flags reflect a
real gate, which matters for both safety and the integrity of the §6 measures.

---

## Data-dictionary change log

**v2 (2026-06-01) — Steps 2/2b (stance)**
Added top-level `stance` column to the `events` table and to every `make_event`
call. `run` events carry `stance=NULL`; `turn` events carry `"peer"`, `"oracle"`,
or `"control"`. The `payload` for turn events also embeds `stance` redundantly
for JSONL consumers that do not join on the column.

**v3 (2026-06-01) — Step 3 (calibrated uncertainty)**
The `turn` payload `telemetry` block gained four new fields: `reasoning_effort`
(string, the per-call effort of the final reasoner draft), `escalated` (bool),
`abstained` (bool, peer-only), and `confidence_trajectory` (object with `planner`,
`reasoner`, `self_eval` floats). The `plan` dict gained `confidence` (float).
These are additive JSON keys; no SQL column change. Pre-v3 rows have these fields
absent in `telemetry`; downstream code should use `.get(..., default)`.

**v4 (2026-06-01) — Step 4 (process-measure extraction)**

*Field-name clarification:* `process_measures.md` v2 refers to the TVD field as
`result.distance`; the **actual key** in `compile_and_run` (and in every persisted
run-event payload) is `result.tvd`. `result.distance` is a generic description in
the spec; `result.tvd` is the canonical key. `measures.py` reads `result["tvd"]`.

*Spec location:* `backend/app/analysis/process_measures.md` (canonical); the root
`process_measures.md` is the authoring copy — keep them in sync.

*Extraction:* `backend/app/analysis/measures.py` implements every §2–§5b
definition from the spec; `backend/scripts/extract_measures.py` produces the three
output files (`measures_by_attempt.jsonl`, `measures_by_participant.csv`,
`calibration_pairs.csv`). Identical input trace ⇒ identical output, byte-for-byte.

*JSONL round-trip confirmed:* all Step 2+3 telemetry keys (`telemetry.escalated`,
`telemetry.abstained`, `telemetry.reasoning_effort`, `telemetry.confidence_trajectory`,
`plan.confidence`, `self_eval.*`, `governance.*`, `stance`, `final_message`) are
stored in the `payload` JSON column and faithfully round-trip through both
`InMemoryStore.export_jsonl` and `SqlStore.export_jsonl`.
