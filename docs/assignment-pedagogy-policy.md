# Assignment pedagogy authorization (PR #13 / issue #20)

Implemented on the PR #13 foundation, `ceef784`, in `fix/pr13-assignment-policy`.
This is standalone Belay authorization, not a deployed Cairn/Waypoint adapter.
It does not authorize other platform connectivity or change an operating budget.

## Trusted grant format

The operator-owned authorization file keeps `exercise_versions` and `subjects`.
Inside a membership, an assignment value may use this explicit object:

```json
{
  "assignments": {
    "echo-1": {
      "version": "v1",
      "generation": "enrollment-1",
      "policy_revision": 1,
      "allowed_pairs": [
        {"mode": "study", "stance": "peer"},
        {"mode": "teach", "stance": "oracle"}
      ]
    }
  }
}
```

Every object field is required; extra fields, wrong types, unknown enums and
invalid revisions reject the configuration. `policy_revision` is a positive
integer, not a boolean. Empty `allowed_pairs` explicitly denies tutoring.
Pairs are exact: the example does not authorize study/oracle or teach/peer.
Browser parameters, enums and selectors never add permissions.

## Legacy migration and updates

The old `"echo-1": "v1"` form is accepted as study/peer only, generation
`legacy-v1`, revision 1. It grants neither teach nor oracle/control. The local
demo's existing generated legacy file consequently becomes study/peer only.
Tests that need control use explicit permissions in temporary synthetic grants.
Malformed new objects never fall back to legacy permissions.

Operators must publish a complete valid file atomically. Increment policy revision
when changing allowed behavior; assign a new generation when access is re-granted.
Do not reuse a revoked generation, including by restoring an old authorization
file. Use explicit grants before managing enrollment changes. The legacy alias is
a migration aid, not a durable re-enrollment protocol.

Current permissions are read before tutoring, every wrapped provider invocation,
each visible SDK attempt including format fallbacks/JSON repairs, and delivery.
SDK automatic retries are disabled so they cannot bypass these checks. Authorized
control turns do not construct a model client, including the saved turn path. Checks are
request-local, bound to the original issuer/audience/subject and class/learner.
Changed configuration, generation, version, revision or behavior ends the request.
A provider call already sent cannot be retroactively undone; this change makes no
refund, cancellation, unknown-cost or platform-accounting claim.

## Saved dialogue

Saved turns retain a content-free internal receipt (principal digest, generation,
policy revision, mode and stance) within the existing turn-response JSON. It is
not returned as dialogue. Replay, history and model-context retrieval require the
current matching permission. Narrowing/re-granting blocks old protected output;
deletion remains available while the learner still has assignment access.
History also checks the original assistant turn's receipt before returning a
student follow-up's quoted excerpt. Failed or pending follow-ups and pagination
cannot bypass this check by excluding the original assistant row from the page.

Pre-upgrade saved assistant turns lack reliable permission metadata. They are not
replayed or injected into tutoring context. The learner can delete that attempt
or start another; no old mode is guessed or backfilled. Changing an unrelated
pair with a new policy revision also invalidates prior receipts conservatively.
No SQL column or migration is added. Saving remains optional and independent of
research consent. This slice does not establish a developer/instructor diagnostic
role or alter the earlier Glass Box work in the separate integration branch.

## Validation and follow-on work

`tests/test_assignment_policy.py` exercises both HTTP edges, all six combinations,
legacy grants, malformed policies, class isolation, changes between inference
calls, before delivery, SDK fallback/repair and protected saved replay/history.
CI explicitly sets `TEST_DIALOGUE_POSTGRES_URL` for its disposable Postgres service,
then asserts that the dedicated migration/retry/concurrency acceptance runs without
skips. CI also runs the frontend Node tests.

PR #14 includes this foundation but has additional queued/saved-job/worker paths.
Those need to carry the same selected behavior, revision and generation and check
them through dispatch, later attempts, staging, publication and recovery. That
integration is a separate remaining blocker under issue #21; passing these PR #13
tests does not certify queued execution or platform readiness.

Issue #22's durable monotonic authorization snapshots, high-water marks across
restart/restore, freshness and transport remain future contract decisions. This
file adapter validates the current file; it cannot detect an operator reverting
to an identical old generation after an unobserved revoke/re-grant cycle.
