# Privacy

This document is meant to be honest about limits, not reassuring. The framework's
privacy posture is enforced by architecture in some places and by layered, fallible
heuristics in others, and the difference matters. Where a protection is deterministic
it is stated as such; where it is best-effort it is stated as such. The central honest
claim is that the leak floor and the wellbeing floor are not equally strong, and the
document says so plainly.

## Identity: pseudonymous only

Identity is a pseudonymous host id and nothing else: a provider-namespaced numeric user
id, for example `gh:12345`, which is also the participant anon-code namespace. The
`/quad/v1/capabilities` document advertises this scheme (`provider:numeric-id`). The
tutor sees pseudonymous ids and submission content; it never receives or stores names,
SIS identifiers, or plaintext email.

The sidecar rejects PII at the boundary, before any parsing or storage, on every route
(`integrations/quad/pii.assert_no_pii`). A name field, an SIS id field, a plaintext
email pattern, or a non-pseudonymous id returns HTTP 422. This is tested:
`tests/test_quad_sidecar.py::test_pii_rejected_email`, `::test_pii_rejected_name_field`,
`::test_pii_rejected_sis_id`, and `::test_non_pseudonymous_id_rejected`.

## No rankings, no grade writes

There are no student-vs-student leaderboards or ranked cohort comparisons; instructor
surfaces are class-level aggregates only. The tutor is formative and never writes
grades. A `gradingspec_result` arrives only as read-only context for a turn, mapped
onto the turn's run-result slot and never written back anywhere. There is no
grade-write route and no write path in the source. This is tested three ways:
`tests/test_quad_sidecar.py::test_gradingspec_result_is_read_only_context` (the result
is read-only context), `::test_no_grade_write_route_exists` (no route), and
`::test_sidecar_source_has_no_grade_write_calls` (no write call in the source);
`::test_capabilities_declares_identity_and_grades_firewall` confirms the advertised
posture (`grades.writes: false`).

## Goals and reflections

A student may set their own goals and record reflections (`agent/goals.py`). These are
pseudonymous, stored on the learner model, and injected only for the tutor's use within
the turn. They are never surfaced to an instructor and are never written to grades. At
intake they pass the same PII boundary as everything else, including over the sidecar
(`/quad/v1/goals`, `/quad/v1/reflection`): an email in a goal returns 422.

## The two floors are not symmetric

A student-set goal is honored only within two floors. The floors are different in kind,
and the framework does not pretend otherwise. This asymmetry is the honest claim the
IRB review and proposals rest on; the fuller record is `docs/EXTRACTION_PLAN.md`
section (g).

### The leak floor is a deterministic, executable, post-hoc gate, and it is supreme

Leak-detection has a ground-truth oracle: the active pack's executable grader plus the
known solution. So whether a draft leaks the answer can be decided deterministically,
after the model speaks, by code that does not depend on the model behaving
(`agent/governance.check` running `pack.leak_evidence`, then `safe_rewrite` on a block).
A student goal is input, never authority. Even a worst-case reasoner that tries to
leak, with a goal demanding the full answer, is caught post-hoc and the solution
stripped. This is proven by `tests/test_goal_safety.py::test_student_rule_cannot_leak`.

### The wellbeing floor is layered defense-in-depth, not a single deterministic gate

Tone has no ground-truth oracle. There is no grader for whether a message is
contemptuous the way there is for whether code solves the exercise, so the wellbeing
floor cannot be a single deterministic gate of the same strength. Its protections are
layered, stated here in order of primacy, and every layer except the provable
never-honor invariant has false negatives by nature:

1. The persona stance is the primary protection. The peer stance carries an explicit,
   non-relaxable wellbeing line (no berating, no reinforcing negative self-talk, not
   even on request). A capable model that follows its system prompt simply does not
   produce contemptuous tone; on a strong model this holds the floor on its own.
2. The intake detector records a harmful goal but marks it not honored
   (`agent/goals.is_harmful`). It is a cautious keyword and shape heuristic, biased so
   that a false positive routes a benign goal to a kind decline (acceptable) and a
   false negative would honor harm (not acceptable). It will miss evasive phrasings.
3. The never-honor-framing guarantee is provable. The prompt builder re-checks the goal
   text, so the honor framing is never applied to a harm-requesting goal regardless of
   the stored flag (a stale or forged `honored: true`). A harm-requesting goal can only
   ever receive decline framing. Tested by
   `tests/test_goal_safety.py::test_honor_framing_never_applied_to_harm_requesting_goal`.
   This closes the "honored but harmful text" path; it does not close the "evade the
   detector entirely" path, because there is no oracle.
4. The post-hoc softener is an observable heuristic backstop, not a gate
   (`agent/governance.soften_if_berating`). It replaces an obviously berating or
   contemptuous draft with a kind redirect and is surfaced in telemetry at
   `telemetry.components.wellbeing_softened`, so an operator can see it firing. Its
   value is highest on weak self-hosted models, which can produce harsh tone in a way
   frontier models rarely do. It is tuned for precision on contempt and passes firm,
   direct, honest correction through unchanged
   (`tests/test_goal_safety.py::test_softener_does_not_soften_firm_but_kind_correction`),
   and it has false negatives by nature.

There is no wellbeing parity with the leak floor. The leak floor is a deterministic
gate backed by an oracle; the wellbeing floor is the best a no-oracle floor can be, and
it is not claimed to be more.

### Distress response is a recorded decision, not built

Goals and reflection intake is a place a student may express genuine distress rather
than a merely counterproductive rule. How the tutor should respond to a
distress-signaling goal or reflection is a product and IRB decision, deliberately left
to whoever owns that call; no speculative distress handling has been built. The safe
defaults recorded for the decider (`docs/EXTRACTION_PLAN.md` section (g), with a pointer
note in `agent/goals.py`) are: do not honor a harmful directive (the wellbeing floor
holds regardless); respond briefly and kindly without reinforcing or amplifying the
distress; do not diagnose; leave deeper support to humans and the institution's own
channels; and treat surfacing any support resource as a deliberate, reviewed choice,
not a default the framework ships on its own.

## The export contract

The research trace carries no PII: events are keyed by the pseudonymous id and the
eight-field row shape (`participant_id`, `ts`, `exercise_id`, `mode`, `event_type`,
`stance`, `payload`, `note`) holds no identity fields. The events model is additive:
new telemetry keys and new `event_type` values are added without changing the row shape
or the `events.jsonl` export contract. Documenting it does not change it.
