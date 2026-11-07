# PR #13 assignment authorization review ? 2026-10-21

## 1. Scope and starting point

Issue #20 and the next Belay implementation slice recommended in #22. Started at
PR #13's exact reviewed head `ceef7844ecb8085c54fe3a8f5ced8ce157d291bf`, on a new
local branch `fix/pr13-assignment-policy`. The existing local UI branch was 41
commits ahead of that head; it was preserved rather than pushed into this PR.
The local main and shared-controls branches were not moved. No worktree, merge,
rebase, force-push, PR change or GitHub comment was made.

This delivers the PR #13 authorization and CI slice. It does not resolve all seven
reviewed PRs, the remaining historical DCO requirement, or #14's queue integration.

## 2. Changes

- Trusted assignment grants now carry version, grant generation, positive integer
  policy revision and exact allowed mode/stance pairs. Old string grants migrate
  to study/peer only. Missing/malformed object policy fails closed; empty pairs
  deny tutoring. No implicit Cartesian product or oracle/control authorization.
- Shared checks cover legacy and Quad tutoring, saved turns, subsequent provider
  calls, visible SDK retries/fallbacks, response release and protected history/replay.
  Request-local checks bind the original issuer/audience/subject and learner scope;
  a changed grant cannot silently sustain an old request.
- SDK automatic retries are disabled. Explicit application retries recheck current
  permissions. Already sent calls are not retroactively undone or refunded.
- Saved turns keep a content-free internal behavior receipt in existing response
  JSON. It counts toward storage bounds and is excluded from public dialogue.
  Prior turns without trustworthy metadata cannot be replayed or used as model
  context. Authorized owners retain the deletion route; no schema change/backfill.
- Authorized control turns no longer construct a model client. Existing synthetic
  HTTP tests explicitly grant their non-default behaviors; real legacy grants
  remain restricted. Saving and research consent stay independent.
- PostgreSQL CI sets TEST_DIALOGUE_POSTGRES_URL, explicitly runs migration/retry/
  concurrency acceptance and asserts JUnit contains executed tests with no skips.
  A Node frontend test job was added.

The grant format and upgrade/update behavior are documented in
`docs/assignment-pedagogy-policy.md` and linked from README.md.

## 3. Validation

Final local code, using isolated test data and synthetic credentials/providers:

| Check | Result |
| --- | --- |
| Complete backend, SQLite | 685 passed, 8 skipped, 0 failed |
| Complete backend, disposable PostgreSQL 16 | 686 passed, 7 skipped, 0 failed |
| Dedicated PostgreSQL migration/retry/concurrency | 1 passed, 0 skipped; JUnit checked |
| New assignment-policy cases | 68, included in the complete suites |
| Assignment policy plus local launcher subset | 87 passed |
| Frontend complete Node suite | 32 passed, 0 failed, 0 skipped |
| Ruff check / format check | Passed; 125 files formatted |
| Mypy, isolated clean cache | Passed; 119 source files |
| Staged diff whitespace check | Passed |

The test host uses Windows CPython 3.13; configured hosted CI uses Python 3.12.
The hosted workflow has not been run on these local commits: no push was made.
The disposable PostgreSQL containers were removed. No paid inference, platform
connectivity, production-scale acceptance or live deployment is claimed.

The first full SQLite/PostgreSQL attempts each timed out in the saved control-turn
launcher test (5-second HTTP wait). Control still constructed a model SDK although
it performs no inference. That construction was removed, a regression was added,
and the unchanged timeout passed in the focused and final full suites. Timing was
not profiled enough to assign every part of the original delay to one cause.
Default-cache mypy runs reported unrelated missing traitlets imports; independent
clean-cache and final isolated-cache runs passed without suppressing errors,
changing type-check rules or installing additional packages.

## 4. Remaining review items

- #14 must adopt the foundation with its own execution grant, selected behavior,
  policy revision/generation, queued worker, saved-job, staging, publication and
  protected recovery checks. None of those paths exists in this PR #13 baseline.
- Current operator file policy is re-read. #22's durable ordered snapshots,
  high-water marks, expiry/transport and restart/restore contract are not supplied
  here. Operators must issue a new generation after re-grant and must not restore
  an old generation; an unobserved identical file rollback cannot be detected by
  this file adapter. Full platform integration remains unverified.
- Original merge commit `ceef784` lacks DCO sign-off and is authored by Annabelle.
  Its historical metadata was not rewritten. New commits use Annabelle's requested
  identity and `git commit -s`; this does not retroactively sign the old merge.
- Other PR blockers #15?#19 and #21 remain separate. Upstream Actions approval
  state and fresh hosted checks still need attention when the fixes are pushed.
- Real runtime, .env, budgets, retained usage and operational databases were not
  modified. Existing untracked review/output/preview artifacts were excluded from
  staging. No prepare, migration, unknown-task replay or service restart occurred.
