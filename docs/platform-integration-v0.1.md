# Belay platform integration contract v0.1 and gap checklist

Status: **Review draft; proposed mechanisms are not approved or implemented.**
Revised: 2026-10-16. Source baseline: 2026-10-15, with Belay authorization and
storage evidence checked again for this revision.

## 1. Scope, sources and settled responsibilities

This draft covers platform identity and assignment context entering Belay, and
Belay requesting inference through Portage. It documents requirements, gaps and
future acceptance criteria. It does not implement interfaces or change application
behavior, start services, call models, or change budgets.


These responsibilities are established direction, not questions to decide again:

| Component or role | Established responsibility |
|---|---|
| Waypoint / Keycloak | Login, institutional identity integration and credential issuance. |
| Cairn | Class membership and enrollment, assignment definitions and versions, student and teacher course interfaces; stable opaque learner identifiers, approved context and current authorization through trusted integration. |
| Belay | Tutoring, scoped learner state, optional conversation persistence, pedagogical safeguards, and enforcement of access and workload limits. It relies on platform identity and does not create an account or enrollment system. |
| Portage | Model selection and routing, authoritative inference budgets and usage accounting, including retries and fallbacks. |
| Outfitter | Compute provisioning, lifecycle and associated resource limits. |
| Platform administrators | Formal quotas and replenishment policy. No budget dashboard expansion is requested. |

Names and email addresses must not reach Belay or Portage. Teacher access to
technical diagnostics remains undecided; this draft grants none. Overall platform
connectivity has not been implemented or verified. Belay's standalone shared ledger
and protections remain until verified Portage integration can take over the relevant
responsibilities. Local test allowances are not formal student policy.

The code baseline is `bb0abf4b48bcd9c7fd7165bf59a1055ce5afa8fd`, originally from
`feature/shared-traffic-budget-controls`. Checked-out branch for this revision
is `platform/contract-v0.1`, at the same baseline. Existing `output/` artifacts are
outside this delivery. External evidence is pinned in section 5.

**Current implementation** means source-supported behavior, not a fresh runtime test.
**Established direction** means the supplied Greg text and review brief. **Proposed** means a mechanism
requiring review/adaptation. **External dependency** means a capability to provide or
verify. **Open question** means a mechanism or policy detail, not reassignment of roles.

## 2. Current boundaries and terminology

See [CONTEXT.md](../CONTEXT.md). Platform assignment versions, learner submission
commits, instructor grading-policy commits and Belay content versions are distinct.
Abbreviated source paths in sections 2-4 are relative to `backend/app/`.

| Boundary | Current implementation and evidence | Integration implication |
|---|---|---|
| Identity | `backend/app/auth.py:65`, `authorize`: RS256, pinned key, issuer/audience, required timestamps, maximum 900-second lifetime. | Reuse verification; no OIDC login, JWKS discovery or overlapping rotation here. |
| Authorization | `auth.py:20`, `Membership`; `auth.py:164`, `_configuration`: operator-owned file read per request. | Extra JWT class claims and browser selectors cannot grant access; no external synchronization API. |
| Content | `auth.py:128` and following checks bind installed version, membership grant and requested version. | One installed version per exercise; Cairn mapping still required. |
| Queued execution | `auth.py:247`, `recheck_grant`; `controls/data.py:242`, `:257`, `:317`; `controls/runtime.py:64`, `model_call`. | Recheck original authority at execution, external attempts, staging, publication and protected lookup. References are not credentials. |
| Pedagogical permissions | `schemas.py`, `SolTurnRequest`; `integrations/quad/schemas.py`, `QuadTurnRequest`. | `mode=study/teach` and `stance=peer/oracle/control` have value validation but no per-assignment grant allowlist. |
| Pedagogical behavior | `agent/orchestrator.py`, `run_turn`, including stance dispatch and governance. | Stance changes execution; oracle permits solutions. Valid enum values do not establish authorization. |
| Models | `agent/llm.py:101`, `OpenAICompatProvider`. | Configurable chat completions, fast/strong tiers, SDK `max_retries=0`; no Portage receipt adapter. |
| Local accounting | `controls/runtime.py:64`; `controls/ledger.py:277`, `settle`. | Reserve per call; missing usage/errors retain unknown liability; local prices are not provider invoices. |
| Storage purposes | `store/scoped.py`, `scoped_store`; `store/consent.py`, `ensure_participant`; `conversations/router.py:109`. | Course state and saving are independent of research consent; config reports `research_consent_required: false`. |

See [authentication](authentication.md), [conversation restoration](conversations.md)
and the [shared-provider audit](../deployment/controls/shared-provider-budget-audit-summary.md).
The later separation in `conversations.md` and current source qualify older consent-coupling
language in `authentication.md`; it must not be read as a research prerequisite.

## 3. Contract A: platform context entering Belay

### 3.1 Reusable protocol and distinct learner states

Currently, an operator supplies the public key and grants; browsers carry short-lived
bearers. The platform issuer is Waypoint/Keycloak; exact audience, claims mapping and
key distribution remain to be agreed. Production issuers require HTTPS. Tokens must
not enter URLs, logs, persistent browser storage or model context. Current `sub` is
opaque and non-PII; learner aliases have the shape `provider:numeric-id`. External
subjects or Git usernames cannot be assumed to satisfy that alias contract. Greg assigns
the stable opaque learner identifier to Cairn; review must settle how it binds to the
Waypoint/Keycloak credential and how Belay accommodates it without exposing identity.
The existing `provider:numeric-id` shape is a compatibility constraint, not Greg's
mandated platform identifier format.

These states must not be collapsed into "registration/consent":

| State or record | Meaning and current boundary |
|---|---|
| Platform login | Waypoint/Keycloak authenticates the learner. Login alone grants no class/assignment access. |
| Access authorization | Cairn supplies current membership/assignment authority through trusted integration; Belay validates it. Today Belay receives operator-maintained grants. |
| Participant initialization | A scoped pseudonymous row supports course state. `ensure_participant` creates missing rows with research consent false and preserves existing choices. This is not account creation, enrollment or permission to tutor. |
| Operational records | Scoped learner state, counters, recovery data and budgets support operation. Unsaved queued Ask uses bounded temporary input/result storage; unsaved does not mean no operational records. |
| Optional conversation saving | A separate learner choice and configured policy control persistence. Current create uses `save:true`; `save:false` creates no saved conversation. Saving, restoration and deletion do not require research participation. |
| Research consent | A separate recorded choice controls research-event routing/use under existing research policy. It neither grants access nor enables saving. |

Ordinary tutoring remains available without research consent and with saving disabled,
subject to authorization and operational limits. Saved dialogue requires configured
policy/schema/deletion ledger and the learner's saving choice, not research consent.
This draft adds no consent flow or retention policy. Deployment retention, backup/deletion
and operational/research data-use rules still requiring approval remain review items.
Changing research consent must not silently change saving preferences or erase/recreate
course state. Conversation deletion does not promise erasure of all accounting records
or independently retained research data.

This is the **existing authorization-file shape**, using synthetic identifiers:

```json
{
  "exercise_versions": {"ds-foundations": "datascience-2026-10-06"},
  "subjects": {
    "host:12345": [{
      "institution_id": "demo-institution",
      "class_id": "demo-class",
      "learner_id": "demo:12345",
      "assignments": {"ds-foundations": "datascience-2026-10-06"}
    }]
  }
}
```

The current endpoint is `POST /api/sol/jobs` (`main.py:109`; `controls/jobs_http.py`,
`AskSubmission`). Headers include `Authorization: Bearer <signed-token>` and, for
membership selection, `X-Belay-Institution: demo-institution` and
`X-Belay-Class: demo-class`. This example matches current submission structure;
execution also needs valid grants, installed pack, controlled runtime and capacity/
budget. Research consent and optional saving are not prerequisites.

```json
{
  "request_id": "demo-request-000001",
  "participant_id": "demo:12345",
  "exercise_id": "ds-foundations",
  "exercise_version": "datascience-2026-10-06",
  "event": "chat",
  "mode": "study",
  "stance": "peer",
  "source": "",
  "recent": []
}
```

HTTP 202 means accepted, not completed inference or settlement. With valid auth
configuration, invalid/missing credentials return 401; inaccessible scope, resource or
version returns 404. Missing/malformed/unreadable configuration returns 503; that check
precedes token validation.

Extra JWT claims cannot expand authority; mere presence is not an access violation.
Unknown fields follow each schema: current `Membership` and `AskSubmission` forbid
extras, while other request models differ. The proposed platform schema needs explicit
version/extension rules; do not reject every token with extra claims or silently accept
new authorization-bearing fields.

### 3.2 Proposed platform launch object: no receiving route yet

This server-to-server review example is not an accepted learner API body or authorization
file. Route, service authentication, limits and JSON Schema remain proposed. Cairn provides
authorized context; Belay validates mapping/policy. The object alone proves no authority.

```json
{
  "contract_version": "0.1",
  "assignment": {"platform_id": "cairn", "assignment_id": "assignment-42", "assignment_version": "release-7"},
  "belay": {"exercise_id": "ds-foundations", "exercise_version": "datascience-2026-10-06"},
  "scope": {"institution_id": "demo-institution", "class_id": "demo-class", "learner_id": "demo:12345"},
  "policy": {"allowed_modes": ["study"], "allowed_stances": ["peer"]},
  "student_visible_context": {"instructions": "Explain your reasoning.", "student_code": "result = {}", "execution_feedback": [{"check": "visible-output-shape", "passed": false, "message": "The output is an empty dictionary."}]},
  "authorization_revision": "revision-17"
}
```

Proposed rules and gaps:

- Resolve Cairn assignment/version to installed content through trusted mapping; reject
  missing, stale or mismatched mappings. Browsers cannot create mappings.
- Derive scope from authenticated authority. Learner identifiers only select/confirm
  existing grants. Pass no names or emails to Belay or Portage.
- Enforce both mode/stance allowlists at intake, execution and publication. Study/peer
  as default is proposed, not approved. Confirm configuration source, updates and migration.
- Greg permits approved assignment context, student code and permitted execution feedback,
  including visible check results. Keep hidden tests, reference solutions and official
  gradebook records outside tutoring; Sol must not write grades. The proposed allowlist
  also excludes rankings, grade history, private reviews and PII. Do not forward Cairn work
  responses wholesale or mistake visible checks for official gradebook records. The example's
  `student_code` and `execution_feedback` structure is proposed; schema, limits and provenance
  need review. Existing PII/governance checks do not supply this teaching-material schema.
- Material is data, not permission to relax safeguards. `authorization_revision` is an
  order/freshness reference, not a credential. Updates must be idempotent; stale updates
  must not restore revoked access. The mechanism is not implemented.

### 3.3 Revocation and unavailability

Currently, atomic grant-file replacement takes effect at the next check. No Cairn-to-Belay
update mechanism or propagation bound exists; readable stale files are not detected.

Specify update ordering/delivery, maximum propagation delay, snapshot validity and stale-source
behavior. Do not fall back to anonymous or expired authority. Issuer unavailability alone
need not invalidate otherwise valid credentials; agreed validity/freshness rules govern use.

Recheck original-subject authority before queued execution, subsequent external calls,
staging/publication/delivery and protected retrieval. Another subject with the same alias
cannot sustain that job. Dispatched calls may not be cancellable/free. Revocation blocks
further work and delivery; known costs/unknown liability remain. No SLA is approved here.

## 4. Contract B: Belay calling Portage

### 4.1 Reuse, authority and proposed correlation

Portage owns routing/model selection and authoritative inference budget/usage accounting.
Belay retains its Provider interface, pedagogical fast/strong requirements and workload
protections. Configure aliases after checking structured output, output limits and reasoning
support. A base-URL change alone does not establish authorization/accounting integration.

Billing attribution derives from verified Belay scope and server-side Portage credentials,
never learner-supplied keys. Do not forward login tokens, raw identity subjects, names,
emails or course-management records to the model service.

The minimum proposed correlation hierarchy is:

- `operation_id`: one tutoring operation, potentially containing several model requests.
- `attempt_id`: one Belay-to-Portage dispatch. Planner, evaluation, revision and explicit
  JSON-repair/format-fallback dispatches each have an attempt and local reservation.
- `provider_attempts[].id`: each Portage-internal upstream attempt, including retries and
  fallbacks, under the originating Belay attempt. It is not a new Belay dispatch.
- `receipt_id` and `receipt_revision`: an accounting receipt and its ordered updates for
  an attempt, enabling reconciliation without repeating inference.

**Proposed binding:** an authenticated Portage connection plus a persisted local mapping
of `(operation_id, attempt_id)` to expected `billing_scope` and reservation. Receipts echo
all three identifiers; Belay checks them against that mapping before settlement. Echoed
fields alone are not trustworthy. Current `model_call` attempt IDs are local; transmission,
receipt storage and remote binding need adaptation. Authentication, ordering and query
transport remain open mechanisms.

These are logical metadata/receipt examples, not supported Portage HTTP fields. Do not
add them to chat-completions bodies without agreed transport/schema. Amounts are synthetic;
no prices or quotas are approved here.

```json
{
  "contract_version": "0.1",
  "operation_id": "operation-demo-1",
  "attempt_id": "attempt-demo-1",
  "billing_scope": "trusted-course-account-1",
  "capability": "tutor-fast-json",
  "max_output_tokens": 512,
  "retry_policy": "no-hidden-retries"
}
```

```json
{
  "contract_version": "0.1",
  "operation_id": "operation-demo-1",
  "attempt_id": "attempt-demo-1",
  "billing_scope": "trusted-course-account-1",
  "receipt_id": "receipt-demo-1",
  "receipt_revision": 1,
  "state": "settled",
  "currency": "USD",
  "cost_microunits": 120,
  "usage": {"input_tokens": 100, "output_tokens": 20},
  "provider_attempts": [{"id": "upstream-demo-1", "state": "settled", "cost_microunits": 120}]
}
```

Proposed accounting states are `settled`, `rejected_before_dispatch` and `unknown`.
They describe accounting, not answer success. Known final costs are nonnegative integers
in the stated currency. In this minimal proposal, a settled total covers all listed
provider attempts, including charged failures, and equals their sum. Fees/adjustments
not expressible this way need a reviewed schema extension. Known aggregate usage covers
all attempts, not just the winning response.

For partial completion, retain known costs on settled provider attempts; mark unresolved
ones `unknown` with `cost_microunits: null`. The parent remains `unknown` with total
`cost_microunits: null`; unknown aggregate usage is `null`, not zero. A returned answer
does not prove accounting is final; all costs may also be settled without any successful
answer. A trusted `rejected_before_dispatch` receipt has no provider attempts and zero
cost. An error status alone is insufficient evidence for that state.

A higher receipt revision may resolve unknowns to a complete settled total. Exact
duplicates are no-ops. Stale revisions cannot regress state; conflicting data for an
existing revision or finalized settlement requires investigation, not history overwrite.
These ordering/finalization rules are proposed, not existing API guarantees.

### 4.2 Failures, retries, reconciliation and transition

| Situation | Required treatment | Current gap or reusable behavior |
|---|---|---|
| Normal result | Bind operation, Belay attempt, billing scope and receipt; assess safety independently of accounting. | Local usage is priced locally; remote receipts are not integrated. |
| Budget refusal | Stop inference; release its hold only on trusted no-dispatch/no-charge evidence. | HTTP 429 or an error string is not proof of zero cost. |
| Timeout, disconnect or missing usage | Retain unknown liability/hold; query accounting without blind redispatch. | Local conservative handling exists; remote reconciliation does not. |
| Portage retry/fallback | Internal attempts belong to the original Belay attempt and Portage's authoritative budget. Bound/reserve the full permitted chain. | Belay SDK settings do not disable Portage retries. Initially propose no hidden retries; enabling a supported retry/fallback policy requires review. |
| Belay JSON repair/format fallback | Each new dispatch gets its own attempt/hold under the same operation. | Preserve `model_call` boundaries; final-answer-only accounting is insufficient. |
| Partial success | A usable response may coexist with unknown costs; retain holds until all costs reconcile. | Do not settle from only the winning upstream attempt. |
| Duplicate/conflicting/wrong-scope receipt | Validate source and local mapping; apply once, reject mismatches, investigate conflicts. | Local `settle` checks idempotence/conflicts; remote validation needs implementation. |
| Delayed receipt/restart | Persist associations; reconcile without re-executing unknown work. | Job recovery is not Portage financial reconciliation. |

Retain Belay's standalone shared ledger and limits until the corresponding Portage handoff
is verified. An authoritative Portage charge and Belay hold represent the same liability,
not two expenses. Proposed reconciliation resolves a hold with the complete authoritative
amount once; it does not add remote charges on top of estimated local charges. Until the
adapter is verified, do not label local estimates authoritative settlement. Outstanding
unknowns survive the transition.

Review administrator-policy/budget-period mapping, retry bounds, cached/reasoning-token
coverage, currency units, reservation release and cutover rules. Policy refresh or model
switching does not create funds. Portage ownership and administrator quota authority are
settled; these handoff details remain proposed.

Greg explicitly accepts USD1 per six-hour period and USD5 per week alongside a separate
cumulative cap for local testing only. This is not authorization to modify the current
installation or a production quota. Every applicable limit must pass; periodic resets
cannot erase usage, replenish cumulative funds or release unresolved charges. Restarting
or switching providers must not reset accounting.

In the integrated system, Belay enforces received policies/reservations and retains bounded
queues, fair scheduling, concurrency limits, prompt/output bounds, bounded tutoring steps
and safe failure behavior. Code execution retains separate run-count, time and resource
limits. These are established requirements, not a new claim that every mechanism has been
verified. Outfitter's provisioned-compute responsibility does not remove Belay's local
execution bounds.

### 4.3 Student-facing explanations and restricted diagnostics

Glass Box direction is established: collapsed by default beneath Sol's response,
with more room for code and conversation. Student explanations should identify the evidence
used and the reason for the kind of help offered, and allow correction of a mistaken
interpretation. Replace internal labels such as `co_reason` and `revisit`, and raw planner
notes, with short learner-facing explanations. Do not present inferred affect as fact.
Remove confidence percentages from the standard student view: model self-evaluation is
neither an established probability of correctness nor a measure of learner understanding.


## 5. External compatibility evidence

Evidence was inspected from tracked source at these commits on 2026-10-15. It is a
snapshot, not current deployment verification. Private/untracked configuration was not
read. Other repositories remain read-only references.

| Repository | Branch and full source commit | Workspace at original inspection |
|---|---|---|
| Cairn | `feature/ui-layout-refactor` / `ed7d4ea61345734483f636fbed98c76bed6fe0f2` | Existing staged/unstaged UI changes and untracked files; evidence from the commit. |
| Portage | `main` / `1fe17d4d154d1156280069e8d773a8b609e873d7` | Untracked configuration and other files, not read. |
| Waypoint | `main` / `5c0a6189a6bceedbf9df9fd16994f874889141b2` | Clean at inspection. |

Paths/line ranges below are relative to the named repository at its pinned commit.

| Reference | Source evidence | Compatibility finding |
|---|---|---|
| Cairn identity | `internal/api/server.go:1040-1054` obtains username/hostUserID, but student login uses host/username; `:1098-1107` stores those fields; `internal/store/models.go:80-84` uses them for rosters. | Stable platform-subject-to-alias mapping needed; existing identity is not a Belay credential. |
| Cairn launch | `docs/course-workspaces.md:25-28` describes navigation without credential exchange/enrollment proof. | Navigation only; no Belay launch/content mapping found in inspected implementation. |
| Cairn version | `internal/api/server.go:864-880` pins grading templates to full commits. | Grading-policy commit is not an exercise/content mapping. |
| Cairn feedback | `internal/api/student.go:64-75`, `:125-151` includes points, grade history, assessments and reviews. | Needs allowlisted conversion; student-visible is not automatically tutoring-safe. |
| Waypoint identity | `course-workspace/README.md:83-87` uses OIDC, PKCE S256 and Keycloak subject UUIDs; `:123-125` describes independent Hub login/roster checks. | JupyterHub contract, not implemented Belay handoff; do not assume identical revocation behavior. |
| Waypoint roadmap | `ROADMAP.md:89-96` calls for Belay identity coordination and versioned contracts. | Mechanisms need coordination; institutional deployment acceptance unverified. |
| Portage aliases | `src/portage/render_config.py:90-107`, `:160-165`, `:223`, `:255` validates aliases and emits capability metadata. | Reusable routing foundation; confirm enabled aliases. |
| Portage retries | `config/profiles/scale2.educloud.settings.yaml:34` sets `num_retries: 2`. | A Belay dispatch can involve multiple upstream attempts; deployed settings unverified. |
| Portage attribution | `config/profiles/scale2.educloud.md:149-159` describes virtual-key tags/metadata and deployment provisioning. | Trusted billing attribution/provisioning remain external dependencies. |
| Portage measurement | `src/portage/measure.py:246-271` aggregates eligible evaluation attempts; `:258-259` excludes availability attempts. | Not a complete billable ledger. A Belay-facing authoritative receipt protocol was not verified in inspected source. |

## 6. Gap classification within established responsibilities

| Item | Status | Required adaptation or verification |
|---|---|---|
| Pinned-key verification, scoped access, content checks | Current implementation | Retain protections/regression coverage. |
| Local grant reread, queued rechecks, unknown holds | Current implementation | Retain; agree Cairn update transport, freshness and propagation. |
| Course state and optional dialogue independent of research consent | Current implementation with configured policy | Preserve separation; validate platform flow and agree deployment values. |
| Per-assignment mode/stance allowlist | Proposed Belay adaptation | Confirm permissions/configuration source, then enforce all entrances and queued execution. |
| Assignment mapping/material allowlist | Proposed Belay adaptation + external dependency | Cairn supplies approved context/versions; agree schema/provenance and validation. |
| Credentials/pseudonymous identity handoff | External dependency + Belay adaptation | Waypoint/Keycloak issues credentials; agree audience, alias mapping/scope and keys. No Belay account system. |
| Current grants/revocation | External dependency + Belay adaptation | Cairn supplies authority; agree ordering, transport and stale-source handling. |
| Routing, authoritative budgets and full usage | Established Portage responsibility; integration unverified | Verify receipt/query interface, upstream coverage and billing scope. |
| Receipt binding/reservation reconciliation | Proposed Belay adaptation | Agree mapping/idempotence; preserve unknowns; verify handoff before replacing protections. |
| Formal quotas/replenishment | Established administrator responsibility | Confirm identifiers, periods and policy propagation; no dashboard expansion. |
| Teacher diagnostics | Open policy question | Decide audience/content separately; no visibility granted here. |

## 7. Acceptance agreement for a small synthetic demonstration

These are **future criteria, not passed tests**. Test filenames identify reusable source
coverage, not results from this revision. No application/integration tests were run here.

Use one synthetic institution, two classes (`demo-class`, `demo-class-b`), one platform
assignment/version mapped to one installed exercise/version, and a few synthetic learners:
one in each class and one in both for scope selection. Use no real names/emails,
production credentials or paid-model dependency.

Demonstrate platform login/credential issuance, Cairn authorization/assignment launch,
Belay requests through Portage and delivery of Sol's checked reply. Use controlled
upstream responses for repeatable failures. Belay-local stand-ins validate contracts
first but must be labelled mocks; they do not prove live interoperability. Connected-service
acceptance must record versions and which components were real/simulated.

| ID | Scenario and pass condition | Existing test source / additional work |
|---|---|---|
| E1 | Complete login-to-launch-to-Portage-to-Sol flow with authorized scope/version and correlated accounting; no names/emails transmitted. | New repeatable integration test and sanitized reference configuration. |
| A1 | Extra claims cannot expand authority. Forged class/learner or unauthorized access is rejected before any model call. Benign extra claims follow schema/compatibility rules. | `test_auth_isolation.py`; add claim mapping. |
| A2 | Reject absent mappings or mismatches between assignment, grant and installed version. | Version checks exist; add mapping cases. |
| A3 | Revoke while queued/running, after a first call and before delivery. Check before execution, subsequent calls and publication/retrieval; after observing revocation, no further call or protected result delivery. Retain incurred/unknown costs. | `test_jobs_worker.py`; add ordering, propagation and delivery cases. |
| A4 | Missing/malformed/expired authority fails closed; connectivity loss follows explicit token/snapshot validity, never anonymous or indefinitely stale fallback. | Configuration tests exist; add freshness. |
| A5 | Mode/stance changes, especially oracle/control, cannot exceed grants. Synchronous, queued, saved-conversation and Quad paths agree. | New enforcement/tests; current enums insufficient. |
| A6 | Approved assignment context, student code and permitted visible check results can reach Sol; official gradebook records, private reviews, reference solutions, hidden tests and PII cannot. Sol cannot write grades. | New conversion tests with positive and negative cases; PII check alone insufficient. |
| A7 | Cross-class requests cannot read/resume/alter/delete another class's state, jobs or conversations, even with identical aliases. | Scoping tests; extend two-class flow. |
| B1 | Bind operation, Belay attempt, billing scope and receipt; represent all Portage provider attempts. | `test_shared_provider_budget.py` is local groundwork; add receipts. |
| B2 | Budget refusal stops inference; only trusted no-dispatch/no-charge evidence releases holds. | Add Portage rejection cases. |
| B3 | Timeout, partial completion, missing usage and restart retain unknown liability; reconciliation never replays inference. Final higher revision settles once. | `test_jobs_worker.py`, `test_controls_ledger.py`; add remote reconciliation. |
| B4 | Duplicate receipts never double-charge; wrong operation/attempt/billing_scope or untrusted source cannot settle; stale/conflicting revisions cannot overwrite accounting. | Add tests matching section 4 fields/local mapping. |
| B5 | Shared limits cover learners/classes per administrator policy across models, Belay repair and Portage retry/fallback. Success does not erase failed-attempt costs; local holds/remote charges are not two expenses. | Shared-ledger tests; add concurrent cross-class/internal-attempt cases. |
| S1 | If required safety/governance checks fail or cannot complete, do not publish unchecked results. Budget exhaustion cannot skip required checks. Appropriate failure/status messages are allowed. | Existing control/governance coverage; inject failure before release/saved publication. |
| S2 | Student delivery uses learner-facing evidence/help explanations, permits correction, and exposes no raw planner notes, self-evaluation or confidence percentage. Inferred affect is not asserted as fact; technical diagnostics require restricted developer access. | Greg's direction; student-surface verification is future work, not a UI change in this revision. |
| C1 | Research consent false permits tutoring. If configured/selected, saving/restoration/deletion work with consent false or true. Consent changes alter neither access nor saving preference. | `test_conversation_http.py`, `test_conversation_lifecycle.py`, `test_saved_jobs.py`; extend platform flow. |
| C2 | Saving off or `save:false` creates no saved dialogue; unsaved recovery is distinct. Restoration returns only scoped eligible content and rechecks grants/version. | Conversation/job tests; add platform continuation. |
| C3 | Authorized deletion clears message/retry content; late completion cannot recreate it. Deleted/expired dialogue stays unavailable after recovery under existing deletion-ledger rules, independent of research consent. | `test_conversation_maintenance.py`, `test_saved_transactions.py`; document residual content-free accounting/deletion records. |

Later delivery must include sanitized reference configuration, version-pinned setup,
repeatable integration tests and recorded outcomes, with failure injection, deterministic
model stubs and explicit external assumptions. Formal quota/retention values need
administrator/institution approval; synthetic values are test-only. This draft does not
claim those deliverables exist or that the demonstration passed.

## 8. Specific review questions and implementation sequence

Responsibilities in section 1 are settled. These questions concern mechanisms/policy
details; recommendations are not approvals:

1. **Identity handoff:** What Belay audience should Waypoint/Keycloak issue, how should its
   credential bind to Cairn's stable opaque learner identifier, and what identifier scope
   and key distribution/rotation mechanisms should be used without names/emails?
   Retain the current verifier boundary until a reviewed adapter exists.
2. **Authorization and pedagogy:** How should Cairn convey versioned grants, revocations and
   mode/stance policy, with what freshness/propagation bound? Is study/peer the default,
   and how are old configurations migrated without silently granting oracle/control?
3. **Portage handoff:** Does authenticated receipt plus local mapping fit Portage's interface?
   Confirm upstream coverage, revision/query rules, partial/unknown costs, policy/reservation
   mapping and evidence needed before retiring corresponding local protections.
4. **Storage policy:** Which approved operational-record, dialogue retention/backup/deletion
   and research-use rules should reference configuration reflect? Keep research independent
   of tutoring and conversation lifecycle. How should deletion work after course access
   ends, given current learner endpoints require current authorization?
5. **Diagnostics:** Should teachers receive technical diagnostics? If so, which fields and
   access restrictions? Until separately decided, this draft grants no visibility.

Suggested implementation sequence after review:

1. Resolve mechanisms, write versioned JSON Schemas/compatibility rules, then OpenAPI once
   routes/transport are chosen.
2. **First code candidate:** per-assignment server-side mode/stance allowlists, explicit
   legacy-policy handling and tests for all entrances/queued execution. This is a gap,
   not a fix delivered here.
3. Adapt context/mapping validation and authorization updates with mocked Cairn/identity
   inputs; preserve scoped state and independent conversation/research behavior.
4. Implement Portage correlation/reconciliation with controlled responses. Retain local
   ledger/protections until verified takeover, including outstanding unknowns.
5. Deliver section 7's demonstration, sanitized configuration and repeatable tests;
   distinguish mocks from connected-platform acceptance. Production changes, paid calls,
   quota changes and dashboards are outside this revision.
