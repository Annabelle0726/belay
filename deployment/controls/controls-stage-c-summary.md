# Stage C: saved Ask, conversation restoration and controlled execution

## C0 — integration baseline (2026-10-10)

Goal: preserve the existing UI/R2 and bring the complete R1/R3 history together.
The actual starting tips were UI `ceef784`, R3 `1585b23`, main `e8725ec`.
The reported R3 `d7fa29b` is historical; no existing history was rewritten here.
Work is on `integration/saved-ask-controls`, created from the UI tip. Local main
is unchanged. Untracked deployment material and local SQLite files were backed up
outside Git before switching; none is staged. Locked live files stay in place.

Files: merged R3 controls/auth/config/tests/docs; resolved both router inclusions,
combined environment/privacy/architecture/validation documentation, retained UI
HTML and its auth/sidecar tests, added controls browser scripts and preserved both
API client exports. Retained pytest's pre-import temporary database isolation.

Result: complete R1 tip `266c23e` is an ancestor of R3; R2 `3a414d6` is an
ancestor of the UI base. No assumption about partial identity merges is needed.
Validation: Python compilation and staged whitespace check passed; signed HTTP
conversation, jobs-worker and grant regression tests: **36 passed, 0 failed,
0 skipped**. Full/backend/browser/PostgreSQL gates remain unverified at this step.
The retained UI still needs controlled API wiring; this merge is not Stage C
completion. Commit: this integration commit (recorded by the next step).

## Minimal implementation sequence and consistency decision

1. Add a content-free job/turn link and reuse R2 methods with an externally owned
   SQL transaction. Saved Ask requires dialogue and controls in the **same physical
   database**, explicitly configured, with both migrations installed. Existing
   R2 data is neither moved nor silently copied. Split-database deployments fail
   closed for saved Ask and need a separately designed outbox/recovery protocol.
2. Submit saved turns into existing admission, begin the R2 lease only at dispatch,
   check current grant/session/revision/expiry at every boundary, and atomically
   commit released dialogue + owned temporary result + job completion. No model
   call runs inside a database transaction. Unknown execution never requeues.
3. Connect existing optional-save UI and unsaved Stage B recovery. Persist opaque
   request pointers before POST; refresh/disconnect only query that request.
4. Exercise synthetic signed identities, model stubs, deletion/publication races,
   crash rollback, duplicate requests and PostgreSQL independent processes. Record
   local demo instructions and the exact remaining limits before updating UI.

R2 default saving, research consent separation, creation-based retention, external
deletion ledger, semester rules and governance vocabulary remain authoritative.
No cancellation button, teacher permission or code-execution job is in scope.

## C1 — shared transaction seam and owned turn link

Previous integration commit: `ea88b26`.
Goal: use the existing R2 transaction and turn contracts inside the coordinator.
Files: `conversations/repository.py`, `controls/{saved,data,ledger}.py`,
`tests/test_saved_transactions.py`. Added an additive, content-free
`control_conversations` table to explicit controls initialization/upgrade. R2
begin/complete accept an owned connection; normal R2 callers retain their existing
behavior. A completion in the outer transaction is idempotent. Shared transaction
rollback removes the assistant write and retains the pending learner turn.

Validation: **25 passed, 0 failed, 0 skipped** (transaction seam, existing
conversation lifecycle/repository and execution-data tests). Ruff targeted checks
and formatting passed after correcting an invocation's working-directory paths.
PostgreSQL, HTTP saved jobs and browser wiring remain unverified/not wired in this
step. Commit: this C1 commit (number recorded in C2).

## C2 — saved HTTP admission, worker and atomic publication

C1 commit: `31fd9ed`. Files: `controls/{saved,data,jobs_worker}.py`,
`conversations/{repository,router,bounds}.py`, `tests/test_saved_jobs.py`.
Both conversation edges now expose owned jobs/config/by-request routes. In
enforced mode the old turns route also enters admission, never synchronous paid
execution. Stable IDs bind original grant, conversation, revision and immutable
input. The worker loads completed history from R2, applies its context/model
bounds, and starts the existing turn lease only after queue dispatch.

Execution/external-call/publication/read checks enforce live original grant,
assignment version, owner, policy, deletion fence, expiry and revision/turn lease.
Released assistant message, encrypted result and job completion share one SQL
transaction. A crash rolls all three back; lease loss stays unknown and is not
model-replayed. Completed receipts survive a lost HTTP response. Dialogue delete
and maintenance erase linked execution content in their transaction. Expiry also
bounds temporary content and cleanup, without touching accounting liabilities.
Saved temporary results omit Glass Box/live analysis fields, matching R2's rule
that these summaries are not persisted or restored. Support recovery renders its
current institution frame; stored dialogue contains only neutral placeholders.

Validation: **47 passed, 0 failed, 0 skipped** (14 new saved integrations plus
existing worker/conversation HTTP and transaction tests). Initial failures from a
wall-clock test fixture and an incorrectly simulated crash were corrected; the
final run passed. Ruff passed; targeted mypy C1 passed. Full mypy, PostgreSQL,
browser wiring and manual visual verification are pending. Saving stays optional;
the strict Stage B operational content screen may reject a sensitive queued input
when distress routing is disabled instead of retaining it. No detector terms or
retention policy were changed. Commit: this C2 commit (recorded in C3).

## C3 — existing UI and request restoration

C2 commit: `0b0469d`. Files: shared `conversation-client.js`, `ask-jobs.js`,
`request-lifecycle.js`, `control-messages.js`, existing dev/widget/embed clients
and their auth/session/page tests. Controlled saved sessions use the new jobs
routes; unsaved clients keep Stage B job admission/recovery. Saving remains off
until explicitly chosen. Local storage holds scoped opaque request/attempt IDs
and preferences only. A lost/unknown request stays query-only after reload and
changed input. Valid replies are acknowledged after UI handling; switching
attempt/identity invalidates late callbacks. Config/history requests have bounded
waiting, including credential refresh, and 204 delete responses are supported.

The existing layout, safe Markdown rendering, consent separation and conversation
controls remain. Waiting/unknown/conflict/unavailable feedback is explicit;
malformed/empty replies cannot become successes. A status check reuses Ask and
Refresh history; no cancellation control was added. Legacy R2 behavior is still
tested when controls are explicitly disabled.

Validation: **70 frontend tests passed, 0 failed, 0 skipped**, including actual UI
client/Session with an offline API, controlled saved refresh/unknown cases and
Stage B page failure/duplicate/late-response checks adapted to the retained UI.
Earlier integration-harness/syntax failures were fixed before the final run.
Diff whitespace check passed. PostgreSQL races, full backend and visual browser
verification remain pending. Commit: this C3 commit (number recorded in C4).

## C4 — failure hardening, PostgreSQL races and no-model demo

C3 commit: `d9812d9`. Files: controls saved/data/HTTP/worker modules, R2 repository/
router/bounds, `app/local_dev.py`, new `controls/local_demo.py`, saved/PG/launcher/
sidecar tests, UI recovery/status handling, CI, configuration/privacy/frontend
docs and `controls-stage-c-protocol.md`.

Result: terminal failed/unknown tasks now mark their original R2 turn accordingly;
accounting holds remain unchanged. Completed reads require the R2 receipt.
Revision denials have a structured conflict code; obsolete jobs cannot infer an
already completed turn. Provider bounds see the configured provider identity.
Protected transport denies caching error responses as well. Recovering an old
request preserves a newly typed question and says it has not been submitted.
The explicit loopback `--controlled-stub` mode provisions a separate demo DB,
signed synthetic account and worker with local-only model factories.

Validation before this commit: **43 targeted backend tests passed**, including
saved jobs, real PG process/race tests, worker and controls HTTP; **21 launcher
tests passed**; **70 frontend tests passed**. PG combined acceptance (saved +
Stage B + R2 migration/concurrency) had **7 passed**. Strengthened the publication-
first race to observe an actual blocked PostgreSQL row lock, rather than rely on
timing. Real Chromium exercised saved completion, reload, lost POST recovery
(one POST only) and deletion with **0 page errors**, blocking non-loopback browser
requests. Screenshot was inspected outside Git in the temporary demo directory.

Full-suite findings: first SQLite run had **739 passed, 13 skipped, 1 failed**
(old sidecar route whitelist; updated to include the controlled endpoints).
First PostgreSQL run had **743 passed, 7 skipped, 15 failed**: the new PG test
helper leaked `_skeleton` into later governance tests' environment. The fixture
now restores that selection with monkeypatch; no governance rule/test was relaxed.
Mypy initially hit a stale pytest cache, then reported four new typing errors;
the cache-independent run passed after fixing those errors. Ruff passed.
Final full SQLite/PostgreSQL and quality reruns remain C5 work, not claimed here.
Commit: this C4 commit (recorded in C5).

## C5 — final browser corrections and complete verification

C4 commit: `b5c0d99`. Goal: verify the integrated user paths and finish all local
quality gates. Files: `frontend/{dev-client.js,widget.html,embed-demo.html}`,
`frontend/tests/turn-pages.test.cjs`, this summary and `VALIDATION.md`.

Result: the minimal embed now instantiates its task client, blocks duplicate
clicks, restores unsaved requests and fences identity/backend changes. All three
pages catch denied recovery initialization instead of leaving an unhandled
Promise. Recovering an earlier unsaved request keeps new input without inventing
a student message for that unsubmitted input. Ask offers status checking for
uncertain outcomes; no cancel control was added. Embed copy reflects the signed,
controlled interface. The other UI structure and optional-save default remain.

Final verification (2026-10-10):

- Full isolated SQLite suite: **748 passed, 0 failed, 17 skipped** in 204.33s.
- Full disposable PostgreSQL suite: **758 passed, 0 failed, 7 skipped** in 246.24s.
  Includes independent signed API/worker processes, exact duplicate admission,
  delete-first and publish-first contention with an observed blocked row lock,
  and process exit inside publication rolling back both conversation and job.
- Frontend: **76 passed, 0 failed, 0 skipped** after the final page fixes.
- Ruff check and format: passed, **155 files** already formatted. Mypy passed,
  **148 source files**. Whitespace check passed. Backend code was unchanged after
  the full-suite/quality runs; the final changes are browser code/tests/docs.
- Real Chromium with non-loopback requests blocked: dev client saved completion,
  refresh, lost POST acknowledgement recovery (one POST, no resubmission), delete;
  embed and widget unsaved completion, saved HTTP 202 admission and refresh.
  Final runs had **0 page errors**; dev layout screenshot inspected outside Git.

The 7 common skips are the intentionally disabled paid/live model evaluation
and 6 verifier-contract cases requiring an absent sibling checkout. SQLite skips
10 additional PostgreSQL-only cases; those ran in the PostgreSQL leg. No paid
model, real student identity/data or production deployment was used. Browser
checks use local signed accounts and the explicit model stub. Browser validation
initially exposed the denied-scope rejection above; it is fixed and regression
tested. Some manual harness assertions incorrectly expected creation HTTP 201
(R2 returns 200), or nonempty completion text in the widget status field, and
repeated synthetic attempts hit the unchanged five-attempt quota. Harness
expectations were corrected and synthetic demo attempts deleted through the
existing owned API; quota and policy were not relaxed. Final checks passed.

Remaining limits: saved execution requires the explicitly co-located SQL schema;
cross-database publication/outbox is not implemented. Unknown model outcomes are
query-only and require existing operator investigation/reconciliation. Production
policy approval, key/backup/cleanup operations, real provider and production-load
validation remain outside this local integration. A staged-but-uncommitted result
is never silently rerun or republished after lease loss. The inherited strict
temporary-content screen can reject an input it cannot safely queue.

Untracked review material still matches its pre-switch backup hash. User local
deployment files and databases remain outside commits. Complete R1 `266c23e`,
R2 `3a414d6`, and the actual R3 starting tip `1585b23` are all ancestors of this
integration. Main is still `e8725ec`. Commit: this C5 change (recorded in C6).
