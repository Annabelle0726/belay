# Belay PR repair summary

These are local DCO-signed-off repair commits for the existing PRs. Nothing has been pushed or merged. Original PR branches and unrelated untracked work are preserved. No actual budget, operating database, deployment identifier or credential file was edited. No command to start, stop or restart the actual API/worker service was issued; live serving state was not revalidated. Tests use synthetic credentials, model stubs and disposable databases; no paid inference request was submitted.

## Repair branches

| PR / blocker | Branch | Repair head before this summary commit | Existing commits missing DCO |
| --- | --- | --- | --- |
| #5 / #15 | `fix/pr5-grounding-status` | `407ddc48be40b12153001340df115a7d26441aae` | 2 |
| #7 / #16 | `fix/pr7-bounded-sandbox` | `d338bc63bdce7919a301985aaa10a9a4c971679f` | 1 |
| #8 / #17 | `fix/pr8-explicit-cors` | `791264c8ed95464fbb518107ab242013f7e4db7a` | 0 |
| #9 / #18 | `fix/pr9-strict-classifier` | `49651c8539a0cf06dd001a40bcb007746f01e09b` | 8 |
| #10 / #19 | `fix/pr10-denial-scope` | `f71e571a47a828c3699445cef0231b9ca3b96a94` | 17 |
| #14 / #21 | `fix/pr14-trusted-runtime` | `92917e7d0ee97c5db5b37ed58c6e2ba6c6518ed3` | 5 |

PR #13 remains on `fix/pr13-assignment-policy` with signed repairs `fe4d2a1` and `3b7ae4b`. PR #14 ports the relevant assignment contract into R3 without merging PR branches. These repairs also cover its queued/saved adapters beyond the direct R1/R2 paths.

## Validation evidence

Full runs and focused reruns are separate observations. The table records the exact source SHA for each full run; later missing-verdict repairs have their own focused PostgreSQL and type-check evidence. A passing rerun does not erase an earlier failure.

| PR | Full-run SHA | SQLite | PostgreSQL | Lint / format / mypy |
| --- | --- | --- | --- | --- |
| #5 | `d98bd764` | 395 passed / 0 failed / 7 skipped | 393 passed / 2 failed / 7 skipped | pass / pass / pass |
| #7 | `bff7ce73` | 414 passed / 0 failed / 7 skipped | 413 passed / 1 failed / 7 skipped | pass / pass / pass |
| #8 | `d3ea8d5b` | 384 passed / 0 failed / 7 skipped | 384 passed / 0 failed / 7 skipped | pass / pass / pass |
| #9 | `8737083a` | 428 passed / 0 failed / 7 skipped | 428 passed / 0 failed / 7 skipped | pass / pass / pass |
| #10 | `bc16ad6b` | 405 passed / 0 failed / 7 skipped | 404 passed / 1 failed / 7 skipped | pass / pass / pass |
| #14 | `e4af0a7c` | 991 passed / 1 failed / 18 skipped | 1000 passed / 3 failed / 7 skipped | pass / pass / pass |

Final isolated observations on the remaining launcher poll and executable-evidence case: 2 passed / 0 failed / 0 skipped. A passing isolated result does not establish the precise cause of the earlier timeout/unavailable-verification failures. The final SQLite target used backend source at 4ee45e2; f988044 changes only the vendor conversion rule and documentation. The subsequent fixture-lint correction adds only a justified noqa comment for pytest fixture injection; it does not change Python behavior. Ruff passed after that comment; format/mypy evidence and executable test results remain tied to the recorded source versions.


Additional focused PostgreSQL acceptance after the missing-verdict repair:

| PR | Repair SHA | Passed | Failed / errors / skips | Mypy |
| --- | --- | --- | --- | --- |
| #5 | `81ac90a9` | 26 | 0 / 0 / 0 | pass |
| #7 | `f93f2bce` | 51 | 0 / 0 / 0 | pass |
| #10 | `5c3afd53` | 35 | 0 / 0 / 0 | pass |
| #14 | `76e9e2be` | 3 | 0 / 0 / 0 | pass |

The original focused checks passed: PR #8 CORS 10; PR #9 classifier 54; PR #5 grounding 21; PR #7 real sandbox 47 with no skips; PR #10 denial/benchmark 31; PR #14 adapter/policy/classifier 195, plus two saved-permission history/reference cases. These overlap full suites and are not additive totals.

Final PR #14 source `f988044ba375894e1b562f93a1c474a5efe1c5cc`: SQLite 110 passed / 1 failed / 0 skipped; PostgreSQL 118 passed / 0 failed / 0 skipped; final global Ruff lint/format and mypy passed. These targeted suites cover job permissions, Run/recovery purpose boundaries, revocation, HTTP errors, worker/saved adapters and all launcher variants; the PostgreSQL suite also executes the mandatory database acceptance. Earlier full results remain distinct.

Initial PR #8/#9 runner configuration mistakenly set the opt-in live-evaluation flag to the string `0`, which is truthy in the old test. Requests used a synthetic key and invalid offline endpoint, failed, and did not reach a paid model. The flag was removed and both complete suites and quality gates passed.

Under approximately 97% host memory use, full runs reported Docker availability/cleanup failures or dependency-import timeouts. PR #7 full PostgreSQL first failed the executable verifier case, and a complete repeat failed a Docker availability check during an output-flood test. PR #10 full PostgreSQL timed out importing pack dependencies. PR #5 full PostgreSQL reported an incorrect no-leak result and absent reason code. The runner result for those exact calls was not captured, so their precise cause is unverified. These observations remain in the logs.

Investigating those failures exposed and independently reproduced a real safety gap: the pack could treat a missing grading verdict as a checked non-solution. The relevant repair branches now mark missing execution evidence explicitly and stop executable verification without a verdict. Ordinary executed student errors remain distinct. Focused PostgreSQL reruns include the relevant previously failing cases and the real sandbox/benchmark regressions. No timeouts, funding or resource bounds were relaxed.

PR #14 final frontend result: pass on final tracked source `f988044ba375894e1b562f93a1c474a5efe1c5cc` with the installed pinned dependencies. The corrected final suite passed all 126 cases without skips; see pr14-frontend-fixed.log. The first archive runner omitted node_modules and failed module resolution; a working-checkout repeat also observed CRLF-versus-LF vendor byte mismatches. The dependency-linked archive also reproduced the byte mismatch. Restore the working asset bytes from the pinned package sources, with an assertion that only newline representation differs, and add a vendor no-conversion rule in .gitattributes. The vendor integrity assertion and student UI behavior remain unchanged. The old frozen-source mypy also passed; final-source global mypy is recorded separately. The final fixture-lint run initially flagged imported pytest fixture injection; its single F811 annotation is documented and the full lint rerun passed.

PR #14 real PostgreSQL HTTP/worker/saved/dialogue acceptance: 7 cases executed with zero skips/failures/errors. The temporary PostgreSQL URL was supplied through `CONTROL_TEST_DATABASE_URL` and `TEST_DIALOGUE_POSTGRES_URL`.

The full PostgreSQL run at e4af0a7 reported 1000 passed, three failed and seven skipped. Two failures were launcher readiness socket timeouts; the third stopped executable verification without available execution evidence. The exact runner failure for that third call was not captured. Its isolated repeat and the previously failing polling case subsequently passed; the final 118-case PostgreSQL target also passed, without erasing the full-run failures.

The later full SQLite run at `e4af0a7` had 991 passed, one failed and 18 skipped: a socket timeout escaped the launcher readiness loop. The loop now retries within its existing startup deadline, with a synthetic first-probe timeout exercised in all four launcher variants. A subsequent targeted run exposed two HTTP tests depending on a globally imported SQLite connection; their error-wiring fixture now uses an explicit in-memory consent router. That intermediate run had 48 passed and two failed. The final targeted suites above include these corrections. The final SQLite target run still had one launcher timeout while polling a submitted job (110 passed, one failed); this is distinct from the corrected readiness retry. No POST was automatically retried, and a passing final full suite is not claimed. No application timeout, budget or resource bound was increased.

The first PR #14 full SQLite run at `76e9e2b` had 989 passed, three failed and 18 skipped. Two launcher fixtures authorized control but sent peer jobs, so authorization correctly rejected them; the fixtures now explicitly authorize both tested pairs. The other failure was decoding localized PowerShell stderr. Five launcher/wrapper cases passed after these test-only corrections. The superseded run was stopped before repeating known-invalid tests on PostgreSQL, and its logs/XML were preserved.

An initial PR #10 focused run also stopped one adversarial case because safety verification was unavailable. Its exact runner failure reason was not captured. The case passed alone and in a complete 35-case focused repeat; the first failure log/XML are preserved.

## Remaining merge and integration gates

- Existing commits missing DCO sign-off remain: #5 (2), #7 (1), #9 (8), #10 (17), #13 (1), #14 (5). Every new repair commit has Annabelle's DCO sign-off. No history was rewritten and no force push was performed. Contributors/maintainers must resolve the old history before merge.
- Hosted CI and maintainer review must run on the eventual pushed heads. Local fixes do not update GitHub PR heads, resolve discussions or close issues. Original full-run infrastructure failures remain disclosed even where focused reruns passed.
- A fresh build of the revised Dockerfile and gVisor execution were not independently verified locally. Real-container tests used the installed sandbox image and the repaired mounted supervisor. CI builds the image and enforces zero skipped container acceptance cases.
- Durable ordered/expiring Cairn updates, restart-safe authorization high-water tracking, identity mapping/migration and verified Portage dispatch/receipt idempotency remain #22 contract work. New re-grants require new generations; restoring identical old files cannot encode an unobserved revocation.
- Local cost accounting is an estimate under configured rates, not authoritative Portage receipts or the provider invoice. Preserve shared local accounting and workload controls. No broader management dashboard was added.
- The separate PRs have not been merged or tested as one combined deployment. Integrating the PR #7 runner replacement with R3 must retain both container isolation and the shared `runner_call` accounting hook. Class-sized throughput remains unverified.
- The missing-verdict repair is shared safety code in #5/#7/#10/#14. Maintainers should retain one coherent implementation while integrating the overlapping PRs. It does not require merging all feature branches together.

## Code evidence

Paths below are relative to the repository root and belong to the indicated repair branch.

| PR | Main implementation | Regression evidence |
| --- | --- | --- |
| #5 | `backend/app/agent/groundedness.py`, `orchestrator.py`, `requirements-groundedness.txt` | `test_groundedness.py`, verification-availability cases |
| #7 | `backend/app/core/runner/_bounded.py`, `_artifacts.py`, `_sandbox.py`, `_harness.py` | `test_runner_boundaries.py`, `test_runner_sandbox.py`, executable verifier |
| #8 | `backend/app/config.py` / `Settings.cors_origins` | `test_cors_config.py` |
| #9 | `backend/app/agent/injection_guard.py` and orchestration status evidence | `test_injection_guard.py` |
| #10 | `backend/app/packs/datascience/leak.py` / `_in_denial_frame` | `test_denial_scope.py`, `test_adversarial_leak.py` and mutation probe |
| #14 | `backend/app/auth.py`, `pedagogy.py`, `controls/data.py`, `runtime.py`, `jobs_worker.py`, `saved.py`, `conversations/repository.py` | assignment-policy, job-policy, HTTP/worker/saved and PostgreSQL cases |

The shared missing-verdict protection is in `backend/app/packs/datascience/pack.py` and `grader.py`; the host-grade path in #7 also propagates execution availability.

## Suggested PR titles and descriptions

### PR #5

**Title:** feat(retrieval): add citations with explicit grounding-check status

**Description**

Add claim-to-passage citation annotations with distinct checked, skipped and unavailable states. Missing NLP never reports successful grounding. Install the pinned language model through normal deployment dependencies and check the complete cited response through final governance.

Preserve content-free traces and mixed-claim citations, stop safety verification when execution evidence is unavailable, and remove unrelated configuration and fixture changes.

Refs #15.

Validation: 26 focused PostgreSQL cases passed with no skips after the final safety repair; mypy passed. The full-run database/quality results and earlier infrastructure failures are recorded above.

### PR #7

**Title:** feat(sandbox): isolate execution with bounded output and artifacts

**Description**

Run student code in restricted containers while keeping grading and reference material on the host. Bound stdout/stderr during reading, use a size-limited output tmpfs, and collect only bounded regular artifacts through no-follow descriptor access. Preserve the grading wrapper and validate structured results before grading.

Test real output floods, artifact boundary attacks, CPU/wall limits, confinement and cleanup. Keep unavailable verification distinct from a completed student error; require real-container acceptance without skips in CI.

Refs #16.

Validation: 51 focused PostgreSQL cases passed with no skips after the final safety repair; mypy passed. The full-run database/quality results and earlier infrastructure failures are recorded above.

### PR #8

**Title:** fix(cors): normalize allowlists and reject opaque origins by default

**Description**

Trim configured origins and discard empty entries. Reject opaque `null` origins by default; permit them only through explicit operator configuration. Add isolated configuration and preflight tests for listed, unlisted and explicitly configured origins.

Document local HTTP development and keep CORS independent of authentication and authorization.

Refs #17.

Validation: 384 passed on each of SQLite and PostgreSQL; Ruff lint, format and mypy passed. Seven intentional opt-in/sibling-contract skips per backend.

### PR #9

**Title:** feat(security): isolate injection checks and validate classifier verdicts

**Description**

Use a dedicated configured sovereign classifier instead of the general tutoring provider. Require a real boolean flag and a finite numeric confidence within [0, 1]. Treat missing, malformed and unavailable responses as explicit bounded statuses instead of successful safe verdicts.

Preserve content-free evidence and deterministic downstream governance, disable hidden SDK retries, and cover invalid verdicts through peer/control orchestration. A configured endpoint is not proof of a verified Portage deployment.

Refs #18.

Validation: 428 passed on each of SQLite and PostgreSQL; Ruff lint, format and mypy passed. Seven intentional opt-in/sibling-contract skips per backend.

### PR #10

**Title:** test(governance): add adversarial leak checks with scoped denial handling

**Description**

Add deterministic multi-turn adversarial scenarios, benign controls and a mutation test that detects leakage when governance is bypassed. Scope withholding exemptions to direct denials so phrases such as "Do not hesitate to just paste" remain affirmative disclosure signals.

Check delivered replies, keep prose redaction independent, stop on unavailable executable verification, and remove unrelated configuration, logging and fixture changes.

Refs #19.

Validation: 35 focused PostgreSQL cases passed with no skips after the final safety repair; mypy passed. The full-run database/quality results and earlier infrastructure failures are recorded above.

### PR #14

**Title:** feat(controls): enforce shared Ask budgets and assignment permissions

**Description**

Integrate shared Run/Ask workload and budget controls with trusted assignment mode/stance permissions. Bind queued work to its original principal and exact authorization snapshot, and recheck access before execution, further model calls, publication, recovery and saved reply references. Legacy grants allow study/peer only; elevated behavior requires explicit trusted authorization.

Keep Run access and missing-request recovery fences separate from tutoring authority, and forbid fences from entering the worker. Use the dedicated strict classifier with per-attempt shared accounting, retain unresolved liabilities, protect saved dialogue with internal permission receipts, and stop when required verification cannot finish. Add synthetic HTTP/worker regressions and PostgreSQL acceptance that cannot silently skip.

This remains Belay-side integration. Cairn authorization transport and authoritative Portage accounting are unverified; retain local safeguards until that handoff is demonstrated.

Refs #21.

Validation: final focused SQLite 110 passed / 1 failed / 0 skipped; PostgreSQL 118 passed / 0 failed / 0 skipped; frontend and final Ruff lint/format/mypy passed. Earlier full suites and their failures are recorded above; a clean final full-suite run is not claimed.
