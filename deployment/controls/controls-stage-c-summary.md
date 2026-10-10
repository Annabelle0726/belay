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
