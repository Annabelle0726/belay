# CC-R2 - Bounded conversation restoration and clear retention rules

*Planning and implementation brief. Written 2026-10-07 for
`feature/bounded-conversation-restoration`, starting from
`feature/auth-class-isolation` at `8868234`. The features below are requirements and proposals, not claims
that conversation restoration has already been implemented.*

Belay should let a student return to their own conversation after a page
refresh or server restart, without confusing classes, assignments or attempts.
Restoring history must not mean retaining dialogue forever or sending the
entire transcript to the model on every turn.

This is the second production-readiness milestone: bounded conversation
restoration with clear retention and deletion rules. It builds on verified
identity and class isolation. Ordinary course use must not depend on joining
a research study.

**Branch dependency:** this branch inherits the authentication work, which
has not been merged into upstream. State that dependency in any PR.
Do not present the inherited changes as new conversation work. If the
authentication PR changes, reconcile this branch deliberately before merge.

Scope: separate course storage from research consent, add authorized
conversation persistence and restoration, implement bounds and lifecycle
rules, and make the minimum frontend changes needed to use them. Shared
traffic controls, budgets, new login services and B1-B4 integration are
separate work.

---

## 1. Read first

- `docs/prompts/CC-R1-auth-class-isolation-review.md`: the authentication
  review, including open host-contract and telemetry issues. Its findings
  describe the earlier reviewed tree; check current code before claiming
  they have been resolved.
- `CONTRIBUTING.md`, `PRIVACY.md`, `ARCHITECTURE.md`, `VALIDATION.md`:
  privacy constraints, safety floors and recorded behavior.
- `backend/app/auth.py` and `docs/authentication.md`: trusted identity,
  class memberships and exercise-version authorization.
- `backend/app/store/models.py`, `repository.py`, `consent.py` and
  `scoped.py`: existing state, research events and consent routing.
- `backend/app/main.py`, `schemas.py` and
  `backend/app/integrations/quad/`: both HTTP surfaces and dialogue inputs.
- `backend/app/agent/orchestrator.py`, `context.py`, `governance.py` and
  `distress.py`: final released responses, context construction and safety.
- `frontend/api-client.js`, `auth-client.js`, `dev-client.html`,
  `widget.html` and `embed-demo.html`: current browser history behavior.
- Existing consent, SQL, sidecar and authentication tests.

At the starting tree, learner state and research events still share the
research-consent storage switch. There is no dedicated durable conversation
store. Do not use the research event export as a chat-history endpoint.

## 2. Separate ownership, course storage and research participation

Keep three purposes explicit:

| Data | Purpose | Rule |
|---|---|---|
| Learning progress | Continue the course and personalize tutoring | Course policy; independent of research participation |
| Saved dialogue | Restore a student's conversation | Separate saving and retention policy |
| Research telemetry | Analyze study participation | Research consent; content-free trace |

The existing `consent` field must not silently become permission to save
dialogue. A student who declines research must still be able to use the
course. Optional saving, if selected by policy, must have its own setting.

Derive all ownership from the verified identity context. Conversation
ownership includes institution, class, assignment/exercise and its version,
learner, and a distinct attempt where appropriate. Define how assignment IDs
map to the existing exercise grants rather than inventing a client authority.

An attempt is a separate learning session on an assignment version, not the
existing count of code submissions. Refreshing resumes the same attempt;
starting a new attempt must be an explicit operation.

Conversation IDs are resource identifiers, not credentials. Every read,
write, list, delete and resume must recheck current membership and ownership.
Scope pagination cursors too. Never fall back to unscoped legacy records.

## 3. Persist and restore a bounded conversation

Add dedicated conversation/message storage and an explicit, repeatable
migration for SQLite and PostgreSQL. Do not assume `create_all` upgrades
existing tables. Do not automatically copy old research events into dialogue.

Store only the learner-facing transcript allowed by policy. An assistant
message must be the final response released after governance, not an
intermediate draft, hidden reasoning, planner output or rejected solution.
Reusing a saved answer must not bypass authorization or safety decisions.

Treat restored assistant messages as server-owned history; the client must
not replace them with invented assistant replies. Accept the new learner
message through a clearly defined input contract.

Define behavior for retries, duplicate submissions, concurrent turns and
worker failure. Use request identifiers and transactional sequencing so a
retry does not duplicate messages. Prevent two overlapping turns from
silently overwriting each other. Do not keep a database transaction open
during a model call. Represent an unfinished/failed turn without fabricating
a successful assistant response.

Enforce separate configurable limits for:

- Incoming message size and request-body size.
- Stored message count and total stored bytes per conversation.
- Conversations/attempts retained per learner and assignment.
- Messages and bytes returned per history page.
- Restored context tokens and reserved response tokens for model calls.

These are storage and context bounds, not the later shared budget system.
Choose measured local defaults and label them as provisional; document exact
overflow behavior. Do not silently delete saved history merely because the
model context window is smaller.

For model context, select a bounded, ordered recent window. A deterministic
window is an appropriate first implementation. If a generated summary is
introduced later, it needs its own privacy, safety, retention and cost review.

## 4. Define retention, deletion and the frontend behavior

Before enabling durable dialogue saving in a real course, agree on:

| Decision | Required answer |
|---|---|
| Saving policy | Optional or a course function; default behavior and student notice |
| Retention clock | Creation, last activity or course end; exact expiry calculation |
| Retention period | Institution-approved duration; configurable without editing code |
| Deletion | Who can request it, what is removed and when |
| Special content | PII and distress handling consistent with existing guarantees |
| Backups | Backup lifetime and prevention of deleted dialogue reappearing after restore |
| Course changes | Behavior on withdrawal, class removal, version change and course closure |

Do not infer these answers from research consent or introduce an arbitrary
production retention period. Until approved policy is configured, durable
dialogue saving should remain disabled; ordinary tutoring remains usable.
Offer configurable mechanisms and document the unresolved institutional choices.

Preserve the no-verbatim-distress-content guarantee. Define a policy-safe
transcript outcome for a distress turn without persisting the triggering
text or a distress category. Preserve the existing PII boundary; identity
pseudonyms alone do not make message content free of personal information.
Dialogue must not be copied into research traces, logs or ordinary exports.

Deletion and expiry must make history unavailable immediately at the
application boundary, including caches and resume APIs. Specify physical
cleanup timing and make cleanup repeatable. An in-flight response or retry
must not recreate a deleted conversation. Backup recovery must respect
deletion records for their required lifetime.

The frontend should restore the authorized attempt after refresh, load
older messages in bounded pages, and offer an explicit new-attempt action.
Explain unsaved, unavailable, expired or deleted history plainly without
revealing another student's resources. Saving preferences and deletion
controls must match the approved policy. Preserve existing UI styling.

## 5. Tests and validation

Keep tests hermetic: temporary keys/databases, stub models and controllable
time. Add meaningful coverage for:

- Refresh and process restart restore only the correct saved conversation.
- Isolation across learners, institutions, classes, assignments, versions
  and attempts; all exposed API paths enforce ownership.
- Research participation does not gate ordinary course functionality.
- Optional dialogue saving does not grant research consent.
- Message, storage, page and model-context bounds, including exact boundaries.
- Retries, concurrent requests and failure between learner and assistant saves.
- Only released assistant responses are persisted.
- Expiry, deletion, cleanup reruns and deleted history not being resurrected.
- Revoked membership and policy-safe PII/distress handling.
- SQLite/PostgreSQL migrations, including existing databases.
- Frontend restoration, new attempts and expired/deleted-history behavior.

Run relevant tests and the full required regression suite, Ruff lint/format,
mypy and frontend checks. Record actual results and skips. Prior auth test
counts do not establish that conversation restoration works.

## 6. Report and expected outcome

Report:

- Branch baseline, inherited dependencies and files changed.
- Ownership model, attempt semantics and API contract.
- Separation of course progress, dialogue saving and research consent.
- Numeric bounds, context selection and overflow behavior.
- Retention/deletion mechanisms, proposed defaults and decisions still open.
- Migration, retry/concurrency and failure-recovery behavior.
- Safety/privacy verification and actual test results.
- Deployment configuration and remaining host/institution dependencies.

**Expected outcome:** a student can resume their authorized saved attempt
after refresh or restart. The system keeps dialogue and model context within
explicit limits, prevents access to other students' histories, and applies
configured expiry and deletion rules. Students can use the course without
participating in research.

This document prepares the next implementation. It does not assert completed
features, approved retention policy, production deployment or upstream merge.
