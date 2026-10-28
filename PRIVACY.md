# Privacy and Safety

This document describes the as-built privacy and safety posture of the framework: what it
stores, what it never stores, and how the distress-routing layer behaves. It is the
IRB-facing record. Every section cites where the behavior is implemented so a reviewer can
read the code against the claim.

This describes behavior as built. Where a decision is still open, it is marked as a
standing IRB item.

Platform-level policy — which infrastructure may hold which class of data, and who
authorizes an exception — lives in one place:
[`educloud/docs/policy/data-destinations.md`](../educloud/docs/policy/data-destinations.md).
This document is that policy's Belay-side pointer; the module-level posture below is what
implements it here.

## Privacy by architecture

Privacy is a structural property, not a policy bolted on afterward.

- **Pseudonymous identifiers only.** A verified opaque subject resolves to an
  institution-issued institution/class/learner authorization context. The learner
  alias keeps the `gh:12345` format; physical participant and anon-code keys are
  class-specific digests. There is no name, email, SIS id or other personal
  identifier in the identity model. Credentials and subjects are never persisted.
  Source: `README.md` (Privacy by architecture), `CONTRIBUTING.md` ("Privacy is enforced
  in code, not by policy"), `backend/app/store/models.py` (participants table: "anonymized
  identity + consent flag. No PII by design"), `backend/app/integrations/quad/router.py`.
- **PII is rejected at the boundary.** Both authenticated HTTP surfaces refuse any payload carrying PII
  (name, SIS/student id, email, ssn, phone field keys anywhere; plaintext email patterns;
  non-pseudonymous ids) with a 422 before it reaches the tutor.
  Source: `backend/app/integrations/quad/pii.py` (`pii_reason`, `assert_no_pii`,
  `PIIRejected`), `VALIDATION.md` Quad sidecar section ("PII is rejected at the boundary").
- **Raw learner text reaches the sovereign classifier only, and only when screening is
  on.** With the CC-B1 injection/jailbreak layer enabled (`INJECTION_GUARD_ENABLED`), the
  learner's message is sent to one destination and one only: the operator-configured
  **sovereign classifier endpoint** (Portage's `classifier` alias on the institutional
  tier). The guard builds its own client and never touches the tutoring provider factory,
  so a deployment configured for a hosted provider cannot receive learner text through
  this path; with the layer off — the shipped default — no learner text leaves the process
  at all. What is recorded is content-free: a bounded status, score and model, never the
  message and never an exception string.
  Source: `backend/app/agent/injection_guard.py`, `backend/app/agent/orchestrator.py`
  (`_injection_turn`), `ARCHITECTURE.md` ("Injection and jailbreak screening"),
  `VALIDATION.md` Slice Q.
- **Content-free trace.** The trace records pseudonymous ids and structured, content-free
  events. Verbatim learner text is not written to the trace, the logs, or any export.
  Source: `CONTRIBUTING.md`, `backend/app/store/models.py` (events table: "append-only
  trace ... never updated, only inserted").
- **Fixed trace row.** Every event is the same fixed eight-field row (`participant_id`,
  `ts`, `exercise_id`, `mode`, `event_type`, `stance`, `payload`, `note`). `event_type`
  values are additive; adding one does not change the row shape or the `events.jsonl`
  export contract.
  Source: `backend/app/store/repository.py` (`make_event`), `backend/app/store/models.py`
  (Event model).
- **Grades firewall.** Grading-spec results are read-only turn context; there is no
  grade-write route and no write path, and the tutor never writes grades. Goals and
  reflections are pseudonymous and never surfaced to an instructor.
  Source: `VALIDATION.md` Quad sidecar section ("Grades firewall"), `README.md`,
  `backend/app/agent/goals.py`.

## Distress-response posture (the wellbeing floor, third layer)

The distress layer reads the learner's message for an explicit distress signal and, when
routing is enabled, routes outward to a human instead of tutoring. It is the third layer
of the wellbeing floor and is different in kind from the other two: the intake harm
detector guards against the learner asking the tutor to be unkind, and the tone softener
guards the tutor's own tone; this layer routes the learner to human support.
Source: `backend/app/agent/distress.py` (module docstring), `VALIDATION.md` Slice G
("distress-routing layer of the wellbeing floor").

As-built properties:

- **Opt-in, off by default.** `DISTRESS_ROUTING_ENABLED` defaults to `false`. When off, no
  detection runs, there is no short-circuit, and behavior is byte-identical to a build
  without the layer.
  Source: `backend/app/config.py` (`distress_routing_enabled` default `False`),
  `backend/app/agent/orchestrator.py` (the `if settings.distress_routing_enabled:` gate
  before `_distress_turn`), `backend/app/agent/distress.py` (docstring: "Off by default").
- **Conservative, explicit-crisis-only detection.** Detection is a narrow, high-precision
  lexical trigger for explicit self-harm / suicidal-ideation phrasing only. It is a
  routing trigger, not a mental-health judgment: it scores no severity, diagnoses nothing,
  and names no methods. It must not fire on academic despair or frustration, which is
  normal struggle (routing that to crisis support would itself be a harm); that is a tested
  negative control. False positives route to support, the low-harm direction.
  Source: `backend/app/agent/distress.py` (`_DEFAULT_TERMS`, `has_distress_signal`, and the
  detection-boundary comment).
- **IRB-tunable vocabulary.** Institutions extend detection with whole-text terms via
  `DISTRESS_SIGNAL_TERMS` (comma-separated), matched case-insensitively as literals; this
  is IRB-owned.
  Source: `backend/app/agent/distress.py` (`extra_terms`), `backend/app/config.py`
  (`distress_signal_terms`).
- **Surfaces institution-configured support; routes to a human.** On a triggered turn the
  tutor pauses, states it is a study tool and not a counselor, surfaces the
  institution-configured support resources, and names the human escalation route. The
  framework ships only neutral scaffolding; it invents no hotline, number, or service.
  Source: `backend/app/agent/distress.py` (`_FRAME_HEAD`, `distress_frame`,
  `frame_from_settings`), `backend/app/agent/orchestrator.py` (`_distress_turn`:
  `intervention="escalate"`, `governance="flag_escalate"`, tutoring suppressed, no
  planner/reasoner/LLM call).
- **The FILL-IN placeholder is never rendered to a learner.** Displayed content is gated on
  `distress_configured` (true only once both the support message and the escalation target
  are replaced). Enabled but unconfigured renders a safe generic frame that points the
  learner outward ("reach out to someone you trust, or your institution's support
  channels") with no placeholder text.
  Source: `backend/app/agent/distress.py` (`distress_frame` configured branch vs generic
  branch), `backend/app/config.py` (`distress_configured` property: `"[FILL-IN"` not in
  either message; the `[FILL-IN: ...]` defaults).
- **Content-free, non-PII trace, IRB-disableable.** The only trace from a distress turn is
  an additive `distress` event whose payload is exactly `{triggered, configured, routed}`:
  no text, no category, no severity, no PII. At goal/reflection intake a distress signal is
  recorded `honored:false`, `floor:"distress"`, `text:None`, so no verbatim distressing
  content is stored. The whole event is gated by `DISTRESS_TRACE_ENABLED` (default `true`),
  which the IRB may set to `false` to suppress even the content-free event.
  Source: `backend/app/agent/orchestrator.py` (`_distress_turn` components.distress
  payload), `backend/app/config.py` (`distress_trace_enabled`), `VALIDATION.md` Slice G
  (trace description), `CONTRIBUTING.md` ("The distress path stores no verbatim distressing
  content and no category").
- **Startup misconfiguration warning.** If routing is enabled but unconfigured, a prominent
  operator warning (no PII, no learner text) is emitted at startup/config-load so a
  half-armed opt-in is caught in deployment testing rather than at the first triggered
  turn. This is visibility only and changes no runtime distress behavior.
  Source: `backend/app/agent/distress.py` (`warn_if_misconfigured`), `VALIDATION.md`
  Slice G follow-up.

### Configuration (owners)

| Env var | Default | Owner | Purpose |
|---|---|---|---|
| `DISTRESS_ROUTING_ENABLED` | `false` | institution | master switch; off means byte-identical behavior |
| `DISTRESS_SUPPORT_MESSAGE` | `[FILL-IN: institution support resources]` | institution + IRB | resources surfaced to the learner |
| `DISTRESS_ESCALATION_TARGET` | `[FILL-IN: institution escalation contact]` | institution + IRB | human escalation route |
| `DISTRESS_TRACE_ENABLED` | `true` | IRB | set false to suppress the content-free distress event |
| `DISTRESS_SIGNAL_TERMS` | `` (empty) | institution + IRB | extra detection terms (comma-separated) |

Source: `backend/app/config.py` (the `distress_*` fields), `VALIDATION.md` Slice G env table.

## Standing IRB items

Two decisions are deliberately left to the IRB and are marked open in the code:

1. **The detection vocabulary and its boundary.** Where the line falls between academic
   despair (normal struggle) and crisis, and how the trigger vocabulary is tuned. The
   shipped `_DEFAULT_TERMS` list is a minimal, high-precision starter, explicitly marked
   IRB-review-required.
   Source: `backend/app/agent/distress.py` (the `_DEFAULT_TERMS` comment), `VALIDATION.md`
   Slice G ("Two standing IRB items").
2. **Whether the content-free distress event may live in the research trace at all.**
   Controlled by `DISTRESS_TRACE_ENABLED`. Even though the event carries no text, no
   category, no severity, and no PII, recording that a distress routing occurred is an IRB
   decision.
   Source: `backend/app/config.py` (`distress_trace_enabled`), `VALIDATION.md` Slice G.

## Related records

- The full distress build narrative and test list: `VALIDATION.md` Slice G.
- System architecture, including the governance gate and the trace envelope:
  `ARCHITECTURE.md`.
- The licensing split: `LICENSING.md`.
# Operational accounting (CC-R3)

Resource accounting metadata uses separate controls tables and does not depend on research
consent. Encrypted temporary execution content lives separately in `control_data`
as described below; it is not an accounting or research record. They contain hashed hierarchical scope keys, opaque operation/attempt
references, policy versions, integer usage, states and content-free reason codes.
They contain no prompts, source code, response text or bearer tokens. Operator
reconciliation records contain opaque evidence references. No institution-wide
usage endpoint is exposed to students.

The early service-only slice accepted opaque references. Stage B implemented
owned expiring encrypted payload/results; Stage C adds the saved-turn link and
same-database publication contract described below.
Accounting/tombstone archival and rejection-record retention require an approved
policy before production rollout. Development accounting is retained indefinitely
to preserve idempotency and audit history. This is not a new conversation archive.
See [operator guide](deployment/controls/controls-operations.md).

## Production identity boundary

`backend/app/auth.py` verifies signature, issuer, audience and time claims, then
resolves only operator-owned membership and assignment grants. Every learner
read/write, registration, event ingress, export and code execution route uses that
context. Another learner or class is uniformly unavailable (404), regardless of
whether records exist. Missing credentials are 401; missing auth configuration
is 503. Explicit local/test modes still require signed credentials.

`backend/app/store/scoped.py` namespaces class state and assignment-version events.
Legacy records without trusted scope are excluded; no automatic ownership backfill
or broad default access exists. HTTP trace payloads retain allowlisted numeric and
boolean metrics plus the authorized version, removing raw source, stdout, notes
and free-text intake from events/exports. Private scoped goals/reflections retain
the existing tutoring behavior. Consent still controls durable versus ephemeral
state; registration cannot change anyone else's consent. The grades firewall and
governance/distress floors are unchanged. See [the identity contract and upgrade
procedure](docs/authentication.md), including retention and offline-tool boundaries.

## Course storage and research consent (CC-R2 step 1)

Scoped HTTP learner state now serves ordinary course continuity independently of
research consent. Research events remain consent-gated and content-free. Dialogue
saving is a separate, default-disabled policy; research consent never enables it.
See [docs/conversations.md](docs/conversations.md).

Saved dialogue is an independently optional course function, disabled until an
institution-approved policy is configured. It uses dedicated bounded tables and
creation-based expiry, not research events or research consent. Sensitive exchanges
retain a neutral placeholder. Deletion fences survive database backup restoration;
operators must retain the independent content-free ledger and retire backups.
Deployment commands, limits and unresolved policy choices are in docs/conversations.md.
### Unsaved Ask operational recovery (CC-R3 Stage B)

When explicitly enabled, Ask uses short-lived encrypted operational input and
results in the shared controls coordinator. This is not saved dialogue or research
consent: research routing remains unchanged. No bearer token or raw login subject
is retained. Input lasts at most queue wait plus execution limit; result retention
is `result_seconds` (300 seconds locally, maximum 3600). Operators must approve
and disclose production retention, restrict database/key access, run
`python -m app.controls.cli cleanup-content` at least every minute, and exclude
these temporary tables from long-lived backups/exports. Encryption is not permission
to retain content indefinitely. Expiry blocks access even before physical cleanup.
PII and verbatim distress are not retained; content-free accounting/dedup records
survive independently. No R2 saved-conversation strategy is changed.

### Saved Ask execution (CC-R3 Stage C)

Saved Ask reuses the existing optional R2 archive, creation expiry, ownership,
revision/turn leases and independent deletion ledger. It requires explicitly
co-located dialogue/controls tables to publish the released assistant reply,
temporary result and task completion in one SQL transaction. There is no
cross-database atomicity claim or automatic data relocation. A content-free link
associates the logical task with one R2 turn; internal model retries remain
separate accounting attempts. Saved temporary results omit Glass Box analysis.
Deletion and R2 maintenance also erase linked operational input/results; expiry
bounds their TTL. Failed/unknown jobs never create a successful empty reply or
requeue themselves. Original-principal authorization is rechecked at worker and
result boundaries, without retaining credentials.

Operators must exclude temporary execution content from long-lived backups and
exports even when it shares the dialogue database. Existing R2 policy/consent
separation and deletion-fence restore checks remain unchanged. See
[the Stage C contract and local verification](deployment/controls/controls-stage-c-protocol.md).
