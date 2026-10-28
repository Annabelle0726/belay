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

## Independent acceptance review — 2026-10-28

Reviewed application source: `ad36ea8990fd2b158ba357e7d9a164037a14c934`.
The user asked to resume the interrupted acceptance, retain the integration branch,
and leave main unchanged. No repair history was redone and no main merge was attempted.

**Decision: not ready for merge or delivery.** Four independently reproduced
acceptance defects remain. Passing targeted tests does not override these findings.
This pass reviews and records them; it does not silently change the reviewed code.

### Confirmed findings

1. **P2 — protected saved replies leak through history quote metadata.**
   `backend/app/conversations/repository.py:238-239` returns `reply_to.excerpt`
   on student rows without checking the authorization receipt of the referenced
   assistant turn. The assistant-row check at lines 222-230 cannot protect a
   page containing only student rows. With an authorized oracle answer followed
   by 40 failed quoted follow-ups (the default page size), narrow permission to
   study/peer and increment the revision. Direct retrieval correctly returns
   404, but the newest history page returns all 40 server-generated oracle
   excerpts. Every student message in the probe was only `Why?`.
   Both the independent reviewer and coordinator reproduced this using disposable
   SQLite databases. Validate the referenced original turn before disclosing quote
   metadata, including pending/failed follow-ups and pagination. This affects
   repaired PR #24 and the integrated implementation under issues #20/#21.

2. **P2 — authenticated trace filtering drops classifier outcomes.**
   `backend/app/store/scoped.py:50-60,94-108` drops the `injection` object and
   its bounded outcome. Real `run_turn` with a synthetic classifier returned
   `safe` and `malformed` respectively, but neither scoped export retained the
   classifier outcome. A flagged result retains only `triggered: true`.
   Ordinary in-memory classifier tests do not cover this persistence boundary.
   Reconcile the closed outcome/category representation with the HTTP privacy
   allowlist; do not broadly admit arbitrary model strings or exception text.
   This fails the integrated evidence requirement in issues #18/#21.

3. **P2 — punctuation-only quoted follow-ups lose a performed check.**
   `backend/app/agent/orchestrator.py:374-389` returns the clarification frame
   after classification, with empty components and no event. A synthetic `?`
   follow-up with a valid reply context produced one classifier call,
   `components={}`, and an empty in-memory export, for both safe and malformed
   verdicts. Preserve bounded evidence for the check that actually happened.
   This is separate from scoped filtering and affects repaired PR #24 and the
   integrated implementation under issues #18/#21.

4. **P2 — the integrated sandbox error shape breaks local-model feedback.**
   `backend/app/core/runner/_harness.py:85` supplies a complete traceback in
   `error`, while `backend/app/controls/local_demo.py:44` treats text before
   the first colon as the exception type. For `raise ValueError('wrong exercise')`,
   the real registered local adapter publishes `Local model stub: Traceback
   (most recent call last) on student line 1 means execution raised an exception`
   instead of identifying ValueError. The complete suite failed this contract,
   the single-test rerun failed identically, and an isolated diagnostic copy of
   the scenario captured both the actual run envelope and released response.
   Student-error status and line 1 survived correctly; the incompatible exception
   representation remains. Normalize this boundary or consume an explicit bounded
   error type, then re-run the saved/unsaved local-adapter flow. Do not weaken
   the assertion or attribute this deterministic failure to host memory pressure.

The first three defects exist in the repaired runtime source; they are not newly
mistyped merge resolutions. The fourth is an integration compatibility defect.
The quote defect was reproduced at the repository boundary,
and the classifier defects through the real orchestrator with synthetic clients.
No live model or identity service was used.

### Requirement and online-state reconciliation

All issue bodies #15-#22 and available PR discussions were read, together with
CONTRIBUTING, architecture/privacy, assignment/authentication/conversation and
repair/integration documentation. Three independent reviewers inspected the
grounding/sandbox, classifier/governance and authorization boundaries.
The grounding/sandbox review was a limited source pass, with no independently
run tests or complete sandbox audit; it found no additional confirmed blocker.
The 47 sandbox test results below are coordinator-collected execution evidence,
not proof of every possible confinement or cleanup property. No exhaustive
security-audit claim is made for the 210-file integration diff.

Minor observation: the integrated `backend/pytest.ini` lost PR #10's `slow`
marker registration. This produces a warning and should be restored separately;
it is not the cause of the failed adapter test.

| Issue | Current online code | Review status |
| --- | --- | --- |
| #15 | PR #5, `407ddc4` | Explicit grounding availability and packaged model present; historical DCO and hosted acceptance remain. |
| #16 | PR #7, `d338bc6` | Bounded sandbox implementation and real-container coverage present; combined local-adapter error contract fails as described above. Historical DCO and hosted acceptance remain. |
| #17 | PR #8, `791264c` | Explicit opaque-origin opt-in and normalization present; no unsigned commits; hosted acceptance remains. |
| #18 | PR #9, `49651c8` | Strict verdict validation present; integrated persistence/follow-up findings above remain. |
| #19 | PR #10, `f71e571` | Scoped denial, final-reply mutation and independent prose-redaction coverage present. |
| #20 | Original PR #13 still `ceef784`; repaired PR #23 is `3b7ae4b` | Trusted exact pairs/legacy migration present in repair; integrated protected-history finding remains. |
| #21 | Original PR #14 still `92a1d35`; repaired PR #24 is `3357ab8` | Dedicated classifier/accounting and queued permission checks present; findings above prevent acceptance. |
| #22 | Platform design issue | Local policy enforcement is implemented in branches. Identity binding/rotation, durable authorization ordering/freshness, authoritative Portage receipts and accounting cutover remain unapproved/unverified contract work. |

The GitHub main baseline remains `89f2597`. All nine inspected PR workflows
report `action_required` with zero jobs, not passing checks and not test failures.
The connected GitHub account reports pull permission only (`push`, `maintain`
and `admin` are false). No PR has a submitted GitHub review; older requested
changes exist as conversation comments on #5/#7 and remain review evidence.

Fresh DCO trailer audit of commits outside upstream/main found unsigned counts:
#5: 2; #7: 1; #8: 0; #9: 8; #10: 17; #13/#23: 1 each;
#14/#24: 5 each. The integrated history contains 30 distinct unsigned commits.
Do not add another person's certification or rewrite history without authorization.
Several PR descriptions and earlier local repair reports still describe older
heads or say the repairs are local-only; live head observations above supersede
those publication-status statements.

### Fresh validation

Evidence directory:
`C:/Users/ASUS/AppData/Local/Temp/belay-integration-20261028-l3hwi00p`.
The frozen `snapshot-ad36ea8` was compared byte-for-byte with its Git archive:
no tracked source differs. It contains no operating environment file.

- Frontend: **126 passed, 0 failed, 0 skipped** (`acceptance-frontend.log`).
- Ruff lint passed; format check passed for **193 files**.
- Fresh non-incremental mypy passed for **186 source files**. The interrupted
  run's earlier diagnostics remain in `mypy.log`; they did not recur in the fresh
  result in `acceptance-mypy.log`. No source/type-check rule was relaxed.
- Real disposable PostgreSQL HTTP/worker/saved/dialogue acceptance:
  **7 passed, 0 failures/errors/skips**, verified from
  `acceptance-postgres-required.xml`. The task-owned container was removed.
- The complete SQLite suite finished: **1111 passed, 1 failed, 18 skipped**
  (1130 collected; zero errors; 25 minutes 30 seconds). `full-sqlite.xml` and
  `full-sqlite.log` retain the failure in
  `test_real_registered_adapter_saved_unsaved_run_recovery_auth_and_accounting[local_stub]`:
  `controlled_runtime_scenario.py:205` expected `ValueError` in the released
  response message. The original failing response was not printed, so this
  full-run log alone does not establish its precise cause. The exact isolated
  test failed again in 22.31 seconds (`acceptance-sqlite-failed-repeat.xml`).
  The diagnostic scenario then captured the incompatible traceback/type fields
  described in finding 4 (`acceptance-sqlite-diagnostic.log`); application source
  remained unchanged. The diagnostic copy only printed synthetic run/reply data.
  Skips comprise 11 PostgreSQL-only cases, six absent sibling-contract schema
  cases and the one opt-in live-model evaluation. The separate seven-case
  PostgreSQL acceptance is not a full PostgreSQL-suite pass.
- The full SQLite run includes **47 real sandbox/boundary cases passed with
  zero skips** (24 runner cases and 23 boundary cases).
- Existing 81-case composition evidence remains earlier evidence, not a new
  full-suite result. The installed sandbox image is used; a fresh image build
  and live gVisor/platform deployment are not certified by this pass.

All seven repair heads remain unchanged and are ancestors of the integration
head. All 202 pre-existing untracked files match their original SHA-256 hashes.
The index has no unresolved entries. Main remains `e8725ec`; upstream/main
remains `89f2597`. The review report is the only intended checkout edit.
