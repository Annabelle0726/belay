# Student Glass Box follow-up

Scope: the student-facing Glass Box and its response boundary only. The existing
inline, default-collapsed placement under the latest Sol answer remains. This
change does not connect Cairn or Portage, change tutoring policy, or alter
conversation retention.

## Step 1 — establish the actual boundary

- The dev client previously displayed intervention labels, inferred affect,
  confidence, planner notes, self-evaluation, and timing fields. The reference
  widget also displayed internal diagnostics.
- Direct turns and the first saved live reply returned internal fields, while
  controlled job results could persist and return the full internal turn to the
  learner. Saved conversation history already retained released dialogue only.
- No protected developer diagnostics endpoint exists; this change does not open
  one or grant teachers access to raw diagnostics. Internal signals remain
  available to the tutoring loop.

Files inspected: `frontend/dev-client.html`, `frontend/dev-client.js`,
`frontend/widget.html`, `backend/app/main.py`,
`backend/app/integrations/quad/router.py`,
`backend/app/conversations/router.py`, `backend/app/controls/data.py`.

Result: response filtering must happen on the server, including first delivery
and temporary controlled results. No test or model call was needed for this
inspection. Gap: a separate developer diagnostic contract remains a later
decision and must require its own authorization design.

## Step 2 — release a grounded student explanation

- Added `backend/app/agent/glass_box.py` to describe confirmed student-visible
  input: a code error, a check needing attention, a completed run, or the
  submitted question. If none is confirmed, it says so rather than inventing
  evidence. It maps internal intervention choices to short student language
  without emitting labels, emotion claims, raw notes, or confidence.
- Direct Belay and Quad turns, the first synchronous saved turn, and controlled
  saved/unsaved job results now return `glass_box` with only `evidence` and
  `approach`. Controlled execution still validates its complete internal turn,
  rejects non-finite values, and stores only the released student result.
  Saved R2 history continues to hold dialogue only; temporary R3 results follow
  their existing expiry/deletion rules.
- The dev client renders these strings with `textContent`. The reference widget
  renders them as text instead of assembling HTML from raw diagnostics. The
  existing Markdown sanitizer for Sol answers is unchanged.

Changed files: `backend/app/agent/glass_box.py`, `backend/app/schemas.py`,
`backend/app/main.py`, `backend/app/integrations/quad/router.py`,
`backend/app/conversations/router.py`, `backend/app/controls/data.py`,
`frontend/conversation-client.js`, `frontend/dev-client.html`,
`frontend/dev-client.js`, `frontend/widget.html`.

Result: the student response paths no longer expose those raw diagnostic fields.
Tests cover direct Quad, saved live/replay, controlled jobs, sensitive and long
internal notes, and the non-finite storage guard. No paid model was called.
Gap: no newly authorized developer view is provided.

## Step 3 — correction and presentation

- Kept the collapsed Glass Box immediately below only the newest completed
  answer. A new Ask or Run removes the prior control without deleting the old
  answer or backend data. Saved history after reload does not invent a new live
  explanation.
- “Correct Sol's understanding” focuses the existing Ask field, suggesting a
  correction when it is empty. The learner edits and submits it deliberately;
  the existing request path carries it into the next tutoring context. This
  button alone makes no model request.
- Updated the fixed browser fixture to the student response contract.

Changed files: the frontend files above and
`frontend/tests/feedback-browser-fixture.js`. Related regression tests were
updated in `backend/tests/test_conversation_http.py`,
`backend/tests/test_conversation_safety.py`, `backend/tests/test_deploy.py`,
`backend/tests/test_jobs_worker.py`, `backend/tests/test_overlay.py`,
`backend/tests/test_quad_sidecar.py`, `frontend/tests/dev-client.test.cjs`,
and `frontend/tests/turn-pages.test.cjs`.

Verification: frontend `npm test`: 107 passed, 0 failed/skipped. Backend full
`pytest -q -ra`: passed with 18 skipped (PostgreSQL isolation, optional live
LLM eval, and absent sibling verifier checkout); 0 failed. Four additional
evidence-case tests passed in a focused run after the full suite was collected.
`ruff check`, `ruff format --check`, and
`mypy app` passed. An isolated browser fixture on port 5177 showed a completed
stub answer, default-collapsed Glass Box under that answer, and the expanded
evidence/approach and correction control. The fixture intercepts requests and
does not call the configured real provider. Browser coverage of all responsive
widths and a live server reload remains unverified. Existing running services,
database, budget, deployment ID, and model configuration were not changed.

Implementation commit: `ef4f140` (local only). This summary is a separate
documentation commit so the implementation commit ID remains stable.
