# CC-R1 - Review trusted identity and class isolation

*Review note. Written 2026-10-07 for `feature/auth-class-isolation`,
reviewed at `24a34b7`, based on upstream commit `89f2597`. This follows
the numbered structure of CC-B1 through CC-B4, but is a review of existing
work, not an instruction to build another feature or merge the branch.*

Belay must verify who is making a request and which class they belong to before allowing access to learner state,
conversations or queued work. A pseudonymous identifier protects privacy;
it does not prove ownership.

This branch adds signed credentials, operator-managed class permissions,
scoped storage, browser credential wiring and deployment documentation.
It contains four commits and does not include the UI refactor or B1-B4.

**Review position:** the branch is a working local implementation of a
proposed authentication contract. It is not evidence of a completed
EduCloud identity integration. There are confirmed telemetry compatibility
issues to resolve and deployment decisions.

No fixes, deployment, push or merge are authorized by this document.
Review each step, distinguish code defects from policy choices, and report
what was verified rather than treating passing tests as production approval.

---

## 1. Read first

- `CONTRIBUTING.md`, `ARCHITECTURE.md`, `PRIVACY.md` and `VALIDATION.md`:
  contribution rules, safety boundaries and the recorded validation.
- `backend/app/auth.py`: credential verification and class authorization.
- `backend/app/main.py` and `backend/app/integrations/quad/router.py`:
  both HTTP surfaces must enforce the same boundaries.
- `backend/app/store/scoped.py` and `backend/app/store/consent.py`:
  physical data keys, event export and consent routing.
- `backend/app/agent/telemetry.py` and `backend/app/analysis/measures.py`:
  the existing producers and consumers of research metrics.
- `frontend/auth-client.js`, `frontend/api-client.js` and the three demos:
  how credentials reach requests.
- `docs/authentication.md`, `frontend/README.md` and `docker-compose.yml`:
  the proposed host contract and required deployment setup.
- `backend/tests/test_auth_isolation.py` and
  `frontend/tests/auth-client.test.cjs`: what the tests actually establish.

The four reviewed commits are:

| Commit | Scope |
|---|---|
| `f4f469e` | Backend identity verification and scoped access |
| `b7289be` | Authentication and isolation tests |
| `7b325e5` | Browser credential wiring |
| `24a34b7` | Deployment configuration and documentation |

Keep the deterministic governance gate, grades firewall, license headers
and no-PII boundary intact. Do not merge unrelated branches while reviewing.

## 2. Review identity verification and class permissions

### What the code does

The host supplies a short-lived Bearer token. Belay checks its RSA signature,
issuer, audience and dates. Only RS256 is accepted, the public key is pinned
by the operator, and token lifetime is limited to 900 seconds. Local/test
environments still require signed credentials.

After verification, Belay uses the token's opaque subject to look up an
operator-owned JSON authorization file. That file maps the subject to an
institution, class, learner alias and exercise-version grants.

Client-supplied identity fields must match that trusted mapping. Class
headers select an existing membership; they cannot create permission.
Missing/invalid credentials return 401, denied access uses a uniform 404,
and invalid authentication configuration returns 503.

### What is reasonable

- The browser cannot grant itself a learner identity or class membership.
- A token cannot choose its own verification key or signature algorithm.
- Both HTTP surfaces use the same authorization dependency.
- Permission changes are read on the next request rather than waiting for
  an old token to expire.

### Decisions still open

**Host contract:** RS256 plus a local authorization file is this branch's
proposal. The inspected local Cairn login handles operator OAuth sessions,
not this learner-token contract. No matching learner-token integration was
established in the inspected siblings. Waypoint's implementation was not
available locally, so this is not a claim that the wider ecosystem lacks one.

Recommendation: present the PR as a proposed Belay contract until Greg
confirms the issuer, token format, subject mapping and authorization source.

**Class roster ownership:** an operator must maintain the JSON grants.
This may be adequate for a small pilot, but is not automatic enrollment sync.
Agree who updates it when students enroll, withdraw or change classes.

**Key rotation:** one public key is supported. Replacing it invalidates old
signatures; overlapping rotation and JWKS discovery are not implemented.
Document this limitation before a pilot.

Permission revocation affects subsequent authorization checks. Do not claim
that it cancels an already-running turn; queue/cancellation work is separate.

## 3. Review state isolation, privacy and trace compatibility

### What the code does

Learner state is keyed by institution, class and learner. Run attempts and
exercise events also include the exercise version. The adapter uses separate
SHA-256 namespaces that fit the existing database columns.

This prevents reuse of old unscoped IDs through the new HTTP paths.
There is no SQL schema change and no automatic assignment of legacy records
to a class. Exports filter the learner's events by granted exercise versions.

### Decisions still open

- Concept memory, goals, reflections and customization are shared across
  exercises within a class. Confirm that this pedagogical scope is intended.
- Old records remain stored but are unavailable through the new paths.
  If continuity is required, agree on an explicit ownership migration.
- Learning state and research events remain coupled to research consent.
  Nonconsenting state remains in process memory. Greg's request to separate
  ordinary course functionality from research participation is still open.

### Confirmed finding: usage fields are discarded

`agent/telemetry.py:UsageMeter.by_component` produces `calls` and `cost`.
The allowlist in `store/scoped.py:_METRIC_KEYS` contains `count` and
`cost_usd`, but not `calls` or `cost`. The HTTP trace filter therefore
discards the existing call count and cost fields when they are present.

This is a schema mismatch, not a request to implement budgets now.
Before accepting the telemetry claim, preserve these numeric fields or
define an explicit conversion, with a regression test using the real
producer's output. Unknown usage must remain distinguishable from zero.

### Confirmed finding: analysis still expects the old payload

The adapter writes `payload.metrics` and `exercise_version`. Existing
`analysis/measures.py` reads `payload.result`, `payload.telemetry`,
`payload.source`, `payload.plan` and other old fields. Several missing
fields fall back to empty/default values.

The unchanged eight-field event row does not make the new payload compatible.
Without an updated reader, exported HTTP traces can yield missing or
misleading measures. The authentication document acknowledges this change,
but documentation alone does not repair the consumer.

Recommendation: version or explicitly detect the new payload and test
the supported measures end to end. Measures requiring removed text should
be marked unavailable, not silently reported as zero. Do not restore raw
learner content to the trace merely to preserve an old analysis.

## 4. Review browser wiring and deployment boundaries

The shared browser helper obtains a token through a host callback, keeps
credentials out of URLs and browser storage, and checks the approved backend
origin before constructing headers. It requests a token for each call so
the host can refresh it.

This is credential transport, not a login service. The host still needs to
provide the callback, learner alias and membership selectors. The tests use
local credentials; they do not establish a working real host login.

Compose mounts the operator's key and grants read-only. Confirm the host
directory is protected and that the authorization file is replaced atomically.
A container read-only mount does not protect a writable host directory.

Confirm HTTPS termination and approved CORS origins in the real deployment.
An HTTPS issuer setting alone does not prove the request connection is secure.
Public health routes remain available even when auth configuration is missing;
use a readiness check or operator procedure that also checks auth setup.

No conversation restoration, queue, budget enforcement or stronger sandbox
is added here. Execution authorization does not replace execution isolation.

## 5. Tests and validation evidence

- SQLite backend suite: **541 passed, 7 skipped**.
- Browser helper suite: **4 passed**.
- Ruff lint and format checks, mypy and Compose configuration: passed.
- The new authentication suite is recorded as **167 cases** in VALIDATION.md.

### What the existing tests cover

Missing, invalid and expired credentials; signature and claim checks;
identity forgery; cross-class and cross-institution access; both HTTP
surfaces; state and export scoping; assignment versions; legacy exclusion;
repeatable registration; consent lookup and frontend credential headers.

### Additional evidence needed

1. Pass real UsageMeter output through ScopedStore and assert that calls,
   tokens and cost survive without learner content.
2. Run a newly exported HTTP trace through the analysis pipeline. Supported
   metrics must be correct; unsupported ones must be visibly unavailable.
3. Verify a host-issued credential and class grant against the agreed
   integration contract before claiming actual EduCloud integration.
4. Verify the final tree on PostgreSQL, or identify that CI result as pending.
5. Check operational behavior for enrollment changes, key replacement and
   incomplete auth configuration.

Keep automated tests hermetic: temporary keys and databases, no institutional
credentials, live identity service or model endpoint.

## 6. Report

Report the following before recommending merge:

- The exact branch, commit and baseline reviewed.
- Confirmed defects, suggested corrections and tests that reproduce them.
- The intended class-level and assignment-version-level data scopes.
- Legacy-data handling and the remaining consent separation requirement.
- Whether trace producers, storage and analysis agree on the payload schema.
- Tests actually run, prior results cited separately, skipped cases and
  deployment checks still pending.
- Host and operator setup required for a pilot.

**Current recommendation:** retain the branch for review, resolve the usage
field and analysis compatibility findings, and obtain agreement on the host
contract and roster workflow before treating it as production-ready.
