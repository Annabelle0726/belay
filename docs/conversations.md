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
