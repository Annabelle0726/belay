# CC-B1 — A local, sovereign guardrail model closes the jailbreak/injection gap

*Claude Code prompt. Authored in Cowork, 2026-08-08, from a Reflexes deep-
dive (Morph's fast turn-classifier product) and a broader provider scan
(`morph-full-and-provider-landscape-2026-08-08.md`, Cowork project). The
prior session's audit found this framework's governance gate covers leak
prevention, tone, and explicit-crisis distress routing — and nothing else.
There is no jailbreak or prompt-injection detection anywhere in this
codebase today, and no general bulk-classification pass over historical
traces for catching patterns nobody wrote a bespoke detector for.

Morph's "Reflexes" (fast hosted text classifiers, ~90ms, $0.001/event) is
the commercial shape of this gap — and it's a non-starter here: it requires
sending raw student conversational content to a third-party hosted API,
which conflicts directly with `PRIVACY.md`'s standing rule that identifiable
student records never reach a shared or commercial endpoint. The scan found
the actual sovereign answer instead: **Meta's Prompt Guard 86M** (mDeBERTa,
86M params, purpose-built for jailbreak/prompt-injection, small enough for
per-turn latency) and **IBM's Granite Guardian** (2B–8B family, Apache-2.0 —
cleaner license fit for this AGPL/Apache-split codebase than Llama Guard's
community license — broader harm/groundedness classifier, reports well on
the third-party GuardBench benchmark, and is also usable for async bulk
reclassification of historical traces). Both are open-weight and
self-hostable on Portage's existing sovereign inference tier — the same one
already serving Gemma 4 E4B for triage — with nothing sent to a third party.

**This prompt is scoped to Belay's side of the wire: the governance-gate
integration.** Standing up the actual model endpoint on Portage's sovereign
tier is Line E infrastructure work (Waypoint/Portage's config, not Belay's
code) and may already be tracked elsewhere — check `~/dev/portage`'s
`config/profiles/scale2.educloud.*` and this repo's own deployment docs
before assuming a new endpoint needs provisioning from scratch. If no
endpoint exists yet, stub the client behind a clean interface and say so in
the report rather than blocking this whole prompt on infra that isn't yours
to provision.*

---

## 1. Read first

- `backend/app/agent/governance.py` — the existing gate shape (leak check,
  tone softener) this needs to compose with, not duplicate
- `backend/app/agent/distress.py` — the nearest existing precedent: a
  narrow, deterministic, off-by-default detector with an explicit env-flag
  master switch (`DISTRESS_ROUTING_ENABLED`) and a content-free trace event.
  **Match this shape closely** — same off-by-default posture, same
  content-free tracing discipline, same "detection is a routing trigger,
  not a judgment" framing — rather than inventing a different pattern for a
  conceptually similar problem
- `ARCHITECTURE.md`'s "The governance gate" section (now carries this
  prompt's own citation, added just before this task) and `PRIVACY.md`

## 2. Add the classifier client

A thin client module (e.g. `agent/injection_guard.py`, name to taste but
follow `distress.py`'s naming register) that calls Prompt Guard 86M (and/or
Granite Guardian, your call whether one model covers both jailbreak and
broader-harm detection well enough or whether both are worth running) via
whatever local inference path Portage's sovereign tier already exposes —
check `config/profiles/scale2.educloud.*`'s `classifier` alias in
`~/dev/portage` before adding a new one; reuse it if it fits, and say so in
the report if it doesn't and a new deployment is actually needed.

**Hard requirements, non-negotiable, matching `distress.py`'s existing
discipline:**
- **Off by default**, a single master env flag
  (`INJECTION_GUARD_ENABLED=false` or similar), byte-identical behavior when
  off.
- **Fail closed on unreachable classifier, but never on the tutoring
  path** — if the local model is unreachable, the turn proceeds ungated
  (log the miss, don't block the student) — matches this platform's
  existing "availability is not evidence" posture (seen in Portage's own
  `failup.py` — same principle, same reasoning, worth citing in your
  code comment).
- **Content-free tracing** — the trace event records that a check ran and
  its verdict/score, never the flagged text.
- **Never scores severity or diagnoses** — same boundary `distress.py`
  states explicitly for itself; a jailbreak-detection flag is a routing/
  block trigger, not a judgment about the student.

## 3. Wire it into the governance gate

Decide, and state your reasoning in the report: does this run pre-generation
(screen the student's incoming message before it reaches the Planner/
Reasoner) or post-generation (screen the tutor's own output), or both? The
distress detector runs on the learner's message; the leak gate runs on the
tutor's output; a jailbreak/injection check most naturally belongs on the
incoming message, same site as `agent/goals.py`'s existing intake harm
detector — but state explicitly why, rather than assuming.

On a positive flag: match this platform's existing escalation vocabulary —
`flag_escalate` already exists (`orchestrator.py`) for exactly this "surface
to instructor, don't just silently block" pattern. Reuse it rather than
inventing a second escalation path.

## 4. Tests

Unit tests for the client (mocked classifier responses — never call a real
model in CI), the off-by-default posture, the fail-open-on-unavailable
posture, and the wiring point. Follow `tests/test_distress.py`'s existing
test shape closely (explicit-only true positives + a negative control) —
this is the second detector of this kind in the codebase and should not
invent a different testing idiom for a near-identical structural problem.

## 5. Report

- Where the classifier endpoint actually lives (existing Portage sovereign
  alias reused, or new — and if new, flag it as an infra dependency this
  prompt could not close on its own).
- Pre-generation, post-generation, or both — and why.
- Confirm off-by-default is byte-identical to today's behavior (same
  no-op guarantee `distress.py` already gives).
- `uv run ruff check .` and the backend test suite both green, net-additive
  count stated (same convention `VALIDATION.md`'s slices already use).
