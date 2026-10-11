# CC-R3 integration review and next steps

## 1. Scope and evidence

Inspected the current HTTP routes, provider hooks, control runtime, admission,
worker/recovery seams, frontend requests, implementation record and operator guide.
Existing modifications to ARCHITECTURE.md, PRIVACY.md and VALIDATION.md are
documentation link corrections; they were preserved. deployment/local was not read.

Authentication and conversation branches remain separate:
- feature/auth-class-isolation: 266c23e.
- feature/bounded-conversation-restoration: 3a414d6.
- local main: 83bd1a9.

No branch was switched, merged or rebased for this review. No live model call,
production database operation or class-sized load test was performed.
The current implementation has a
working shared-control service layer and guarded SDK/runner hooks, but the
student HTTP workflow does not submit or execute owned queued jobs.

## 2. Findings verified in current code

| Finding | Evidence | Meaning |
| --- | --- | --- |
| Real HTTP turns do not establish operation context | backend/app/main.py:118-166; backend/app/integrations/quad/router.py turn handler; runtime.py:44-57 | Routes check current context, then call the synchronous tutor/runner. They do not derive trusted scopes or submit jobs. |
| Enforced mode rejects missing context | runtime.py:44-57; HTTP enforcement tests | A safe rejection gate exists. Switching the flag does not create authenticated queued execution. |
| Development bypass skips reservation when no context exists | runtime.py:60-68; config.py:26 | Existing local workflow can call providers directly. This is code behavior, not a finding about a running deployment's configuration. |
| Visible SDK attempts are metered | agent/llm.py:102-122, 178-220 and Anthropic attempt path | SDK retries are disabled; explicit fallback/repair calls cross model_call separately. |
| No concrete production worker adapter/launcher found | controls/worker.py:19-24; tracked-source search for run_one, operation and submit | The worker is a tested integration seam. It is not wired to the student HTTP loop. |
| Completion allows no result | controls/admission.py:283-311; test_controls_admission.py:110 | authorized=True can mark a job completed with result_ref=None. An opaque ref alone also does not prove a retrievable, owned result. |
| An error can make a job failed while usage/slots remain unknown | controls/worker.py:62-70; runtime.py:108-113, 155-158 | Money is conservatively held, but the public job outcome needs clearer uncertainty semantics. |
| Heartbeats have no immutable execution deadline | admission.py:261-269; worker.py:44-54; contracts.py:84-85 | A healthy heartbeat can keep stalled execution alive. Worker liveness and execution progress are different facts. |
| Manual reconciliation already exists | controls/cli.py; maintenance.py:69-127 | Missing recovery is not total: executable operator commands exist. Termination is an evidence-backed assertion, not a command that kills external work. |
| HTTP 200 with malformed JSON can become apparent success | frontend/widget.html:154-163, 203-220 | json().catch returns {}; the click handler displays '(no message)' and appends an empty tutor turn. Independently reproduced with the actual post helper and a stubbed response. |
| Frontend request lifecycle is incomplete | frontend/dev-client.html:129-158; api-client.js:15-25; widget.html:203-220 | No stable operation ID, bounded waiting or stale-response guard. Buttons are not locked against duplicate submissions. |
| Network error handling differs between demos | dev-client.html catch; widget.html send handler; embed-demo.html catch | It is inaccurate to say every surface lacks catches. Widget lacks an outer catch; dev client catches rejections but has no bounded wait. |
| Operator example path is stale | deployment/controls/controls-operations.md:40 | From backend, use ../deployment/controls/controls-policy.example.json instead of ../docs/controls-policy.example.json. |

Frontend defects are demonstrated or inferred from code under the stated
failure conditions. No claim is made that a deployed learner experienced them.

## 3. Keep these distinctions explicit

- Job outcome: what usable result exists for the learner.
- Usage outcome: reported, settled or unknown financial/resource liability.
- Worker lease: permission for this worker to continue acting on this job.
- Execution deadline: maximum allowed lifetime of the active operation.
- Client wait deadline: how long the page waits before showing a recovery state.

A valid answer can arrive without usage fields. In that case the learner may
receive a validated completed result while accounting remains unresolved.
Do not convert every unknown charge into a failed answer.

A transport timeout can leave both provider execution and usage uncertain.
Do not show it as definitely unexecuted or invite an automatic new paid request.
A page ceasing to wait does not prove the server or provider stopped.

No user-facing Ask cancellation button is proposed. Preserve useful backend
cancellation, revocation and shutdown mechanisms.

## 4. Phase A: fixes independent of other feature branches

Continue on the existing CC-R3 branch; no new worktree or branch merge is needed.

1. Require a usable result contract before completed:
   validate result shape, ownership and persistence, and reject missing refs
   for result-bearing jobs. Specify what result expiry means without repeating
   model execution. Replace the test that accepts completion without a result.
2. Separate execution uncertainty from accounting uncertainty in job/status
   responses. Failed means no usable result; it must not imply zero spending
   or safe automatic re-execution.
3. Add an immutable active execution deadline distinct from queue wait and
   renewable lease. Propagate bounded provider/runner limits. A deadline
   prevents further attempts/publication; it cannot prove an in-flight external
   call stopped. Retain uncertain slots/holds pending termination evidence.
4. Correct frontend transport and response handling:
   bounded waiting, catch/finally cleanup, schema/nonempty-answer validation,
   synchronous in-flight guard and stale-response protection.
   Preserve the last valid answer when a newer request fails.
5. Correct operator paths and document who investigates unresolved work,
   what evidence is needed, escalation timing and safe restoration.
   Retain the existing CLI; extend it only where recovery is genuinely missing.

Acceptance: malformed 200 responses are rejected; duplicate clicks do not
start overlapping requests; late responses cannot overwrite a newer exercise
or identity; completion without usable results fails; heartbeats cannot extend
the total deadline indefinitely; uncertain work receives no optimistic refund.

Limit: UI guards alone cannot deduplicate across reloads, tabs or lost HTTP
responses. Do not promise full recovery before Phase B's server contract exists.

## 5. Phase B: authenticated Ask without saved conversations

Recommended first integration target: one real Ask path without persistent
dialogue. It needs Step 1's approved identity contract; it does not require
every Step 2 conversation feature to be merged first.

Do not assume permission to merge feature branches. Identify the approved
upstream base and required adapter contract with Greg. Keep the current R3
fixes reviewable independently. After approved prerequisites land, synchronize
the integration work to the agreed base; avoid maintaining duplicate auth code.

Implement the following as one complete vertical slice:

1. Verified identity/current grants -> trusted control Scope.
2. Stable logical request ID + fingerprint bound to route, scope and
   assignment/version. Same ID with changed input conflicts.
3. Atomic admission -> owned job ID; bounded expiring input/result storage,
   independent of research consent or saved-dialogue settings.
4. A concrete worker adapter and runnable worker lifecycle. Load permitted
   input, reauthorize, execute under operation(...), validate and persist result.
5. Owned status/result endpoints, with current authorization on every read.
6. Frontend submits once, polls within bounds and resumes the same job after
   disconnect/reload. Persist only a scope/origin-bound recovery identifier,
   never credentials or hidden permanent chat content.
7. Replay completed work without new inference/charges. An uncertain outcome
   enters recovery, not automatic resubmission.

Cover /api/sol/turn, /quad/v1/turn and /api/run through the shared boundary;
a successful Ask integration must not leave an uncontrolled alternate path.

Acceptance: a stubbed HTTP Ask reaches admission, a real adapter/worker,
runtime reservation, validated result storage and owned retrieval.
Verify repeated submit, lost response, cross-scope access, denied budget and
a crash between result persistence and job completion. Recovery must reuse the
stored result rather than regenerate it.

The development bypass remains explicit. Enforced integration tests must not
obtain Scope from participant_id or pseudo_id fields.

## 6. Phase C: saved conversation integration

After Step 2's approved contract is available:
- Acquire/revalidate conversation revision and pending execution at dispatch;
  queue waiting must not consume the active turn lease.
- Recheck ownership, assignment version, deletion and expiry before work and
  publication. Revocation/deletion must prevent later publication.
- Preserve turn replay and operation replay as one logical request.
- Recover a crash after dialogue publication but before job completion without
  generating another answer, charging again or appending duplicate turns.
- Define cleanup of queued input and published/temporary results, including
  saving disabled and conversation deletion.
- If job and conversation storage are separate databases, do not claim a single
  atomic transaction. Use an idempotent publication/recovery protocol and test
  its crash windows explicitly.

Acceptance: deleted/revoked/expired work does not publish; stored dialogue and
job state can be reconciled after failure without resurrecting content.
Course functionality continues without research participation.

## 7. Verification performed and further gates

Independently rerun on 2026-10-09:
- Five backend control test files: 37 passed, 2 skipped, 1 deprecation warning.
  Application database overridden to a unique temporary SQLite file;
  control fixtures use temporary databases. PostgreSQL test URL deliberately
  cleared; the two independent-process PostgreSQL tests therefore skipped.
- Existing frontend message tests: 2 passed.
- Standalone Node probe of the actual widget post helper: HTTP 200 + malformed
  JSON returned status=200,data={} and would display '(no message)'.

These are focused checks, not new full-regression or PostgreSQL load results.
The recorded SQLite 423/9 skipped and PostgreSQL 425/7 skipped results were
confirmed in controls-implementation.md, not independently rerun.

Add fault tests for duplicate delivery, disconnect, corrupt/empty response,
worker crash, runtime deadline, permission revocation, result write failure,
job finish failure and saved-conversation publication/deletion races.
Use independent PostgreSQL workers for shared limits; later run class-sized
traffic with latency/queue/concurrency/reconciliation measurements.

Greg still needs to approve actual limits, budget periods, class weights,
pricing/gateway treatment, retention/archival and operator responsibility.
Uniform conservative pricing currently differs from provider invoice pricing;
CPU/memory containment and resource costs are not implied by wall-ms accounting.

## 8. Report after each implementation slice

Report exact base/dependencies, changed paths, new behavior, actual tests/skips,
failure demonstrations, remaining gaps and unresolved operational decisions.
Mark service-layer completion and learner-flow completion separately.
Do not reuse full-suite counts to claim end-to-end readiness.

Proposed implementation sequence: independent correctness fixes -> authenticated
unsaved Ask -> saved-conversation integration -> policy approval and realistic
class load. This is a recommendation, not authorization to merge or deploy.
