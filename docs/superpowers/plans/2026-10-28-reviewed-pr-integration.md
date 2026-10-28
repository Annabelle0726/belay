# Reviewed PR Integration Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan inline. Steps use checkbox syntax for tracking.

**Goal:** Combine the seven reviewed PR repair heads on a new local integration branch, without changing main or the original branches.

**Architecture:** Start from fetched upstream/main and merge the repaired runtime, assignment permissions, retrieval, sandbox, CORS, classifier, and adversarial benchmark histories. Resolve overlaps by retaining every reviewed safety contract, rather than taking one entire side indiscriminately.

**Tech Stack:** Python/FastAPI, SQLAlchemy SQLite/PostgreSQL, Docker sandbox, JavaScript browser client, pytest/Node/Ruff/mypy.

**Spec:** User request to create a new branch and merge all repaired PRs; docs/reviews/pr-repair-summary.md on fix/pr14-trusted-runtime records source contracts and prior limitations.

## Global Constraints

- No git worktree; keep the existing workspace on the new branch.
- Preserve original branch refs and unrelated untracked files.
- Do not merge into main, force-push, rewrite history, edit real budgets/databases/secrets, restart actual services, or submit paid model requests.
- Use Annabelle <3141330934@qq.com> with DCO sign-off for all new commits.
- Keep authenticated scope, exact behavior grants, revocation, optional conversation persistence, unknown liabilities, deterministic safety checks, and bounded sandbox execution.
- Local source heads and untracked-file hashes are recorded in the task-specific temporary evidence directory.

## Review Focus

1. Sandbox execution must still enter the shared runner accounting hook.
2. Classifier sends must retain dedicated-provider isolation and per-attempt model accounting.
3. Citation formatting and answer rewrites must not bypass final governance or misreport unavailable checks.
4. Legacy or changed grants must not revive saved or queued work; Run and recovery fences must not gain tutoring authority.
5. Defaults and configuration merges must not re-enable opaque origins, insecure execution, real paid tests, or opt-in CI skips.

## Task 1: Merge the reviewed histories

Files: existing application, tests, CI and documentation changed by the seven source branches; integration ledger at docs/reviews/pr-integration-summary.md.
Consumes: exact repaired source heads; produces one branch containing all seven as ancestors.

- [ ] Record starting refs and preserve untracked-file hashes.
- [ ] Merge fix/pr14-trusted-runtime, then fix/pr13-assignment-policy, then the five focused repair branches in dependency order.
- [ ] Resolve each conflict against the original source contracts; inspect changes rather than using blanket ours/theirs.
- [ ] Commit each completed merge with DCO.
- [ ] Run git merge-base --is-ancestor for all seven heads and scan for conflict markers.
Expected: every source is an ancestor and no unresolved index entries/conflict markers remain.

## Task 2: Validate the combined behavior

Files: backend/app/core/runner/__init__.py and sandbox helpers; backend/app/agent/{injection_guard,orchestrator,groundedness}.py; backend/app/{auth,pedagogy}.py; backend/app/controls; corresponding existing tests and minimal integration regressions if a previously uncovered interface breaks.
Consumes: merged application; produces verified compatibility fixes and recorded test results.

- [ ] Run lint/collection and focused auth, model accounting, sandbox, citation, CORS, and adversarial cases in an isolated test environment.
- [ ] For an actual integration failure, establish its root cause and capture a failing behavioral test before making a minimal compatibility fix.
- [ ] Run the complete backend suite, frontend suite, lint/format/mypy and explicit PostgreSQL acceptance where available.
Expected: report actual pass/fail/skip counts and preserve earlier failed attempts; do not treat focused checks as a full green run.

## Task 3: Review and deliver

Files: docs/reviews/pr-integration-summary.md.
Consumes: final diff and validation evidence; produces a signed-off integration branch and plain-language report.

- [ ] Obtain one fresh whole-branch review of safety integration boundaries.
- [ ] Address important findings with regression evidence; record deferred limitations.
- [ ] Verify seven-head ancestry, protected untracked hashes, original refs and final git status.
- [ ] Commit the report with DCO; leave the integration local unless publishing is explicitly requested.
Expected: exact integration head and sources, conflict decisions, tests and remaining limits are reviewable.
