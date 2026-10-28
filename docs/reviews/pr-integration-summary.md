# PR integration record

Plan: docs/superpowers/plans/2026-10-28-reviewed-pr-integration.md

Base: 89f25971749f9b6c557fc49ab6beaf4a9909bb95

Branch: feature/integrate-reviewed-pr-fixes

## Decisions

- Ruling: Proceed with the explicitly requested inline merge on a new branch, without worktrees or another permission handoff. Original branches remain intact.
- Ruling: Use this repository ledger and task-specific temporary evidence directory rather than unavailable cloud-skill helper executables on the Windows device.
- Pre-flight: runtime/auth/saved adapters overlap PR13; classifier overlaps PR9; grading and runtime execution overlap PR7; citation formatting overlaps governance. Preserve the runtime bindings and all reviewed safety checks.

## Sources

- fix/pr14-trusted-runtime: 3357ab842111b979eb1d656d12ea3cadbe0de181
- fix/pr13-assignment-policy: 3b7ae4b70b1eb9c0df6d31400956d61334b469fd
- fix/pr5-grounding-status: 407ddc48be40b12153001340df115a7d26441aae
- fix/pr7-bounded-sandbox: d338bc63bdce7919a301985aaa10a9a4c971679f
- fix/pr8-explicit-cors: 791264c8ed95464fbb518107ab242013f7e4db7a
- fix/pr9-strict-classifier: 49651c8539a0cf06dd001a40bcb007746f01e09b
- fix/pr10-denial-scope: f71e571a47a828c3699445cef0231b9ca3b96a94

## Progress

- Task 1 started: base and seven source heads recorded; 202 untracked files protected by hash.

- PR14 merged as a4afc46.
- Ruling (PR13): Keep the reviewed runtime permission/receipt/response boundary as a superset of direct R1/R2 behavior. Retain PR13 additional rechecks before JSON repair and saved replay, with runtime accounting still mandatory. R3 PostgreSQL no-skip acceptance supersedes the narrower duplicate CI job.

- PR8 merged as a06d890; runtime already had the corrected default allowlist.
- Ruling (PR9): Preserve the runtime dedicated classifier with physical-attempt accounting, explicit 400/422 fallback, and propagated budget/access denials. Its strict verdict validation and traces already include PR9; avoid a redundant components refactor. Keep PR9 deployment settings, documentation and regression evidence. Preserve isolated database fixtures and trusted synthetic grants.

- PR9 merged as d7e2526.
- Ruling (PR5): Apply citation/status and final-response governance changes while retaining injection screening, authorization, Retry-After headers and isolated test fixtures. The focused PR intentionally removed other feature files; those deletions are not appropriate in the combined branch. Restore the reviewed CORS normalization, and retain only PR9 dedicated-classifier configuration (no duplicate guessed-model fields).

- PR5 merged as 99c2b4e.
- Ruling (PR10): Keep scoped denial handling, adversarial corpus and delivered-response governance changes. Preserve the integrated classifier, CORS, authenticated HTTP routes, execution availability/status and test database/grant fixtures instead of applying unrelated focused-branch deletions.

- PR10 merged as 7681109.
- Ruling (PR7): Keep bounded container output/artifact validation and host-side grading, while retaining integrated authentication, classifier, CORS and test isolation. Restore exactly one shared runner accounting boundary per physical execution and carry informational error status/line through the new result schema; never execute student code on the host.
- Task 1 compatibility evidence: before the adapter patch, existing composition tests had 4 failures/21 passes (missing runner accounting and execution status). New focused metadata regression had 4 failures/5 passes after correcting an over-specific assertion. After the patch, all 81 container, accounting, verification and feedback tests passed with zero skips. Ruff lint and format checks passed.
- Ruling (latest user instruction): Publishing the reviewed integration branch is now authorized. Main and original branch histories remain unchanged; no force-push or automatic GitHub PR merge into main.
