# Bounded conversation restoration

Implementation branch: `feature/bounded-conversation-restoration`, baseline
`6124598`, inheriting authentication at `8868234`. Authentication is an unmerged
dependency; no B1–B4 or UI-refactor branch is merged here.

## Step 1 — separate storage purposes

HTTP learner state (concepts, goals, reflections and overlay) now uses the scoped
course store regardless of research participation. Participant initialization
creates a missing pseudonymous FK row with research consent false and never
changes an existing consent decision. Research events retain consent-based
durable/ephemeral routing. Direct legacy ConsentRouter users keep their original
store interface; HTTP ScopedStore composes course state and research events.

Saved dialogue will use dedicated tables and its own policy/learner preference;
the research `consent` field never grants dialogue saving. Saving remains disabled
until an operator explicitly configures approved retention and backup/deletion
rules. Ordinary tutoring remains available while saving is disabled.

CC-R1's inherited usage-field and analysis-reader findings remain open; this
milestone does not claim that inherited trace analysis is repaired.

## Step 2 — ownership and migration

A saved attempt has a server-generated ID and belongs to the verified institution,
class and learner namespace plus the granted exercise and deployed version.
Each attempt has an independent ordered revision. All storage operations use the
same indistinguishable 404 for inaccessible, expired or nonexistent attempts.
Old research events are never imported as messages. Create retries use an opaque
request ID and return the same attempt; creation quotas are serialized per owner
and assignment. Retention is fixed from creation rather than extended by activity.

With workers stopped, run `python -m app.conversations.migration` from `backend`
against the configured DATABASE_URL. Migration v1 adds dedicated conversation,
message, turn, quota-lock and schema-version tables; reruns verify the schema and
preserve existing data. It supports SQLite and PostgreSQL dialect upserts.
The application fails closed on an absent/incompatible dialogue schema.
Saving remains disabled by default. No guessed ownership or legacy backfill exists.

Step validation: seven hermetic SQLite migration/ownership/retry/failure tests.
PostgreSQL validation and the public API integration follow in later steps.
