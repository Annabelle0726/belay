# CC-R3 Stage B implementation record

User authorization: integrate the complete R1 identity branch into **local** main,
then synchronize R3 and implement unsaved Ask. No push, remote merge, deployment,
branch deletion, paid model, learner cancel button, semester-rule change or R2
saved-dialogue policy change is authorized.

## B0 — local identity baseline integration

Starting checkout was `feature/ui-conversation-preview` at `ceef784`, not R3.
No tracked modifications were present. Twelve untracked local deployment/report
files were preserved in place. Readable files were copied to a private temporary
backup; the live SQLite database received a consistent online backup. Its
transient launcher lock remains in place. No credentials/data were staged.

Reviewed `CONTRIBUTING.md`, `CLAUDE.md`, R1 authentication documentation/review
and CI. Required gates are signed conventional commits, hermetic tests, lint,
format and typing. No hard rule requiring remote approval before an authorized
local main update was found. R1's review note does not itself authorize merging;
the user's current instruction supplies that authorization. Production host/roster
agreement and full-text analysis compatibility are not claimed by this local work.

Prepared `codex/r1-main-integration` from local main `83bd1a9`, merging the entire
`feature/auth-class-isolation` tip `266c23e`, including its launcher commit. Did
not substitute the UI branch or assume its identity-core ancestry included that
tip. Resolved main imports with Starlette responses/CORS retained, and retained
main's database/shared fixtures alongside R1's real signed HTTP test credentials.
No R2/UI feature branch was merged.

Validation: full backend **562 passed, 7 skipped** on isolated SQLite and
**562 passed, 7 skipped** on disposable PostgreSQL. The skips are the opt-in
live-model benchmark and missing sibling verifier-contract cases. Browser auth
tests **4 passed**; Ruff lint/format and mypy (101 files) passed. No model endpoint
was used. This validates local integration, not a production identity rollout.

R1 integration committed as `e8725ec`; local main fast-forwarded to it. R3 now
merges that approved local main. Conflict resolution retains both R1 identity
checks and R3 accounting/error/timeout guards. The combined HTTP tests use real
signed credentials and fresh pack/router wiring rather than anonymous fixtures
or test-order-dependent import state. Frontend authentication and lifecycle
fixtures were combined: **27 passed**. Identity/admission/execution coverage
passed apart from those corrected HTTP fixtures; the corrected HTTP suite is
**6 passed**. Ruff and mypy pass. Full combined regression follows the slice.

## B1 — original-principal execution grant

R3/main synchronization: `a621963`. Added an opaque issuer/audience/subject/scope
reference to verified Identity and immutable exercise/version execution grants.
Worker reauthorization reloads the same operator authorization configuration;
no token or raw subject is stored in the grant. A different subject sharing the
learner scope cannot keep the original task authorized. Key/config errors,
revocation and assignment/deployment-version changes fail closed.

Validation: five new signed-identity grant cases pass; existing identity and
HTTP error suites pass together. Ruff lint/format pass. This supplies authority
only: no HTTP queue or actual worker adapter yet.

## B2 — owned temporary execution data and atomic publication

Added encrypted input/pending-result/result tables in the existing coordinator,
separate from research traces. Ownership is the original grant + scope + exercise
version. Input expiry is admission time + queue wait + execution bound. Result
TTL is policy `result_seconds` (local default 300, bounded to 3600); production
retention approval remains an operator prerequisite. Failed/unknown terminal
inputs and pending output are removed; completed results expire independently.
Content-free dedup tombstones/accounting survive cleanup. Operator command
`cleanup-content` owns physical cleanup when idle; reads always enforce expiry.

Admission/input insertion and result publication/completion share one coordinator
transaction. No orphan data after rejected/conflicting admission, no completed
job without its validated owned result, no automatic rerun after a pre-publication
crash. Existing backend cancellation/reconciliation mechanisms remain intact.

Operational storage checks PII even in source and refuses unsafe content. The
existing enabled distress short circuit keeps only its content-free routing flag;
verbatim distress is discarded before encryption. Detector vocabulary is unchanged.

Validation: execution-data + distress suites **18 passed**; admission/external
metering regression **27 passed, 2 skipped** before the two additional data cases.
New cases cover rollback, expiry, duplicates, revocation and pending-result crash.
Ruff passes. HTTP/worker/client wiring follows; this is not yet an end-to-end Ask.
