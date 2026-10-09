# Stage B readiness: unsaved Ask through shared controls

Reviewed 2026-10-09 after Stage A commits `3eecbb3`, `9729f42`, `d02bdde`.
This is an integration plan, **not an implemented HTTP job API**. The first
vertical slice is Ask without saved conversation history. Saved conversations
remain Stage C; learner-initiated cancellation is not an acceptance condition.

## Verified dependency boundary

The current branch has no `backend/app/auth.py` or conversation repository.
`app/main.py` and `app/integrations/quad/router.py` still call
`controls.runtime.current()` without creating a trusted operation. Thus:

- `development_bypass` retains the existing synchronous development path.
- `enforced` refuses expensive requests without trusted context. It does not
  submit them to admission, run a worker, or supply a protected status/result API.
- The frontend deadline/gate improves local failure behavior only. Refresh or
  another tab/device cannot recover a server operation yet.

Read-only inspection of `feature/auth-class-isolation` at `266c23e` found:

- `app/auth.py:authorize` verifies signed bearer credentials, current
  operator-owned membership and assignment versions, and puts `Identity` on
  `request.state.identity`. Reuse this contract once it is on an approved base.
- `Identity` provides institution/class/learner, `storage_id`, assignment/version
  and `active_assignments`. These support scope derivation and lookup ownership.
- The current identity object does **not** expose an issuer/subject-bound opaque
  grant reference or a token-free live worker reauthorization function. This must
  be supplied by the identity integration. Merely finding the same learner in
  some other subject's membership is insufficient after the original grant is
  revoked. Do not save bearer tokens or reconstruct authority from request IDs.

Read-only inspection of `feature/bounded-conversation-restoration` at `3a414d6`
found `ConversationStore.begin/complete/fail/delete` and revision-based turns.
Stage B does not require copying or merging this whole branch. Stage C must reuse
those publication/deletion contracts after the approved dependency is available.

## Smallest implementation sequence after the identity prerequisite

1. **Trusted operation boundary.** Derive `Scope` from verified identity and a
   stable operator-configured deployment ID. Record an opaque live-grant reference
   and the authorized exercise/version snapshot. Recheck that original grant at
   dispatch, before each external attempt and before publication/result lookup.
   No client-selected institution/class/learner becomes authority.
2. **Owned, expiring execution data.** Add bounded operational input/result
   storage using the existing SQLAlchemy coordinator architecture. Keep content
   separate from content-free accounting and research traces. Define and approve
   operational TTL, cleanup ownership and disclosure for unsaved Ask; unsaved
   conversation history does not mean that recovery needs no temporary data.
   Do not silently put non-consenting learner text in durable research storage.
3. **Idempotent HTTP admission.** Add a job submission/status contract for both
   HTTP edges, with a stable logical operation ID created before first send.
   Fingerprints bind route, trusted scope, exercise/version and immutable input.
   Repeated ID/same fingerprint returns the existing job; changed input conflicts.
   Avoid orphaning payload rows on duplicate/rejected submission. Keep expensive
   synchronous routes fail-closed in enforced mode so they cannot bypass the queue.
4. **Actual worker adapter.** Use `Admission` and `run_one` with a real grant/TTL
   adapter and existing tutor loop/accounting. Only queued work is claimable;
   unknown work is never automatically retried. Queue wait, payload expiry,
   heartbeat lease and immutable execution deadline are separate clocks.
5. **Atomic result publication.** Validate a nonempty usable response, current
   ownership/version and result expiry before completion. Prefer a transaction
   joining owned result persistence and `Admission.finish` in the same database.
   An opaque string alone is insufficient. If publication crosses databases,
   use an idempotent publication receipt/recovery protocol; never assume atomicity.
   Crashes after provider completion must recover a stored result or stay unknown,
   rather than execute the model again.
6. **Recovery in the client.** Persist only a scoped opaque operation pointer,
   without prompts or credentials, and recover/query the same operation after
   network loss/refresh. Respect polling limits. Retrieve results only through
   authenticated ownership checks. Distinguish queued, running, completed,
   definitely failed, expired result and unknown outcome. Missing/expired results
   must not become blank successes or trigger a new model call.

The exact route names and TTL policy are integration choices, not already
available endpoints or approved production policy. There is no need to introduce
a second queue, authentication implementation or conversation system.

## Required acceptance evidence

- Real signed test identities enter HTTP admission; forged/missing identity
  cannot execute. Two learners/classes cannot inspect each other's jobs/results.
- Two API processes and controlled workers share one PostgreSQL coordinator:
  combined concurrency/allowances stay bounded and class fairness remains visible.
- A stable operation submitted concurrently, retried after a lost response, or
  recovered after reload executes one logical turn. Deliberate model-format repair
  remains separately accounted per external attempt; it is not a duplicate turn.
- Worker crashes before/after sending, after storing a result and around completion
  do not rerun unknown work or publish twice. Late fences/deadlines reject writes.
- Revocation of the original grant and assignment/version change prevent dispatch
  or publication, even if another subject still has the same learner scope.
- Missing usage retains its hold while a valid answer can be delivered. A lost
  result retains uncertainty; reconciliation and proof of stopping remain separate.
- Input/result TTL, failed submission cleanup, lost result expiry, unavailable
  coordinator and polling limits have meaningful HTTP/frontend outcomes.
- Research consent does not alter tutoring or grant access; operational recovery
  data respects the approved retention/privacy contract. No cancel button is needed.

Use temporary PostgreSQL, signed synthetic identities, provider/runner stubs and
offline browser tests. No paid provider, deployment or branch merge is implied.
