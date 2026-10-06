# Trusted identity and class isolation (production phase 1)

Both HTTP surfaces use `app/auth.py:authorize` and `store/scoped.py`. The host
obtains a short-lived access token from its identity service; Belay never accepts
an identity asserted by the browser, requests identity-service secrets, or calls
an identity service while handling a learner request.

## Credential and authorization contract

Set these environment variables before launching uvicorn (the application does
not load `.env` itself):

| Variable | Default | Contract |
|---|---|---|
| `BELAY_ENV` | `production` | `production`, explicitly `local`, or explicitly `test` |
| `AUTH_ISSUER` | empty | Exact JWT issuer; HTTPS required in production |
| `AUTH_AUDIENCE` | empty | Audience identifying this Belay deployment |
| `AUTH_PUBLIC_KEY_FILE` | empty | Operator-pinned RSA public PEM key, at least 2048 bits |
| `AUTH_AUTHORIZATION_FILE` | empty | Operator-owned authorization JSON, never writable by learners |

Requests carry `Authorization: Bearer <access-token>` over HTTPS. Only **RS256**
is accepted; the token cannot select a key URL, key file, or another algorithm.
Signature, issuer, audience, expiry and issued-at are verified. `iss`, `aud`,
`exp`, `iat`, and `sub` are required. Optional `nbf` is verified. Dates must be
integer seconds; token lifetime must be positive and at most **900 seconds**.
The subject is an opaque non-PII identifier (1–128 ASCII letters, digits, `_`,
`.`, `:`, `-`). Tokens carrying extra institution, class, learner or assignment
claims do **not** grant permissions. Do not use names, emails or SIS identifiers
as subjects. Belay stores neither the token nor the subject.

Authorization is supplied separately by the trusted operator:

```json
{
  "exercise_versions": {"ds-foundations": "datascience-2026-10-06"},
  "subjects": {
    "host:12345": [{
      "institution_id": "institution-opaque-a",
      "class_id": "class-opaque-a",
      "learner_id": "gh:12345",
      "assignments": {"ds-foundations": "datascience-2026-10-06"}
    }]
  }
}
```

Institution/class IDs are opaque ASCII letters, digits, `_`, `-` (1–64).
Learner aliases use the established `provider:numeric-id` shape (maximum 64).
Exercise/version identifiers are opaque ASCII letters, digits, `_`, `.`, `:`,
`-` (1–64). These are institution-issued pseudonyms, never personal identifiers.
One subject can have several class memberships. In that case supply both
`X-Belay-Institution` and `X-Belay-Class`; the headers select an existing
membership and cannot create one. A single membership can omit both selectors.
Duplicate membership scopes and malformed authorization configuration fail closed.

`exercise_versions` binds the **installed pack content** to its deployed version.
The operator must change this mapping when publishing changed exercise content,
and deploy pack + mapping together. Belay serves one installed version per
exercise; it does not load historical exercise content. A request's optional
`exercise_version` must match the installed version and the membership grant.
Omitting it selects the server's installed version, never a browser-selected
version. Old-version grants can authorize old trace export, but cannot execute
or tutor the current version. The curriculum lists only currently authorized
exercises and includes `exercise_version` for each.

Replace the authorization file atomically to change or revoke membership/grants.
It is validated and re-read on each request, so existing tokens do not retain a
revoked permission. The pinned key is also re-read; replacing it invalidates old
signatures immediately. Coordinate replacement with the host issuer. This phase
supports one pinned key per deployment, not JWKS discovery or overlapping key
rotation. Protect the files with operator-only filesystem permissions and mount
them read-only in the container. The service holds only the public key. With
Compose, put `identity.pub` and `authorization.json` in `AUTH_CONFIG_DIR`
(default `./deployment/auth`, git-ignored); the container uses `/run/belay-auth`.
Set issuer/audience in the Compose environment. From source, set both file paths
to the operator-owned files explicitly.

## HTTP behavior

All `/api` curriculum, participant, run, sol/turn, goals (GET and POST),
reflection, overlay and session export routes, plus all `/quad/v1` turn, goals,
reflection, overlay and events POST routes, require the same authorization
contract. The Quad router protects itself even when mounted in another app.
`/healthz`, `/quad/v1/health` and the content-free capability description remain
public. Events is still an acknowledgement-only ingress, not a grade-write route.
There is no separate staff/service role granting access to learner data.

Body `participant_id`, `pseudo_id`, `learner_id`, `anon_code`, `institution_id`
and `class_id`, when supplied, must equal the trusted context. Resource path
`pid` must be the same learner. Mismatches return the same **404**
`resource unavailable` as denied membership/assignment access; no lookup of the
other learner is performed. Missing/invalid credentials return **401** with a
Bearer challenge. Missing, unreadable or invalid auth configuration returns
**503** for protected requests, including production with a non-HTTPS issuer.
Health can still be used to diagnose a deployment; it does not attest to auth
readiness. Local and test modes still require signed tokens and authorization;
there is no anonymous/development bypass. They only relax the issuer HTTPS rule.

Participant registration returns the authorized learner alias, rather than
minting a new client-selectable identity. Repeated registration updates only
that class learner's consent and is an atomic SQL upsert. SQL consent is read on
each store resolution so another worker's withdrawal is visible on the next
request. Consent remains coupled to storage as before: consenting state/events
use the durable store; nonconsenting/unregistered state/events use ephemeral
memory. Sidecar registration still uses the submitted consent (default false).
Existing retained research records follow the existing retention policy; this
change does not delete historical data on withdrawal or implement consent decoupling.

## State and trace isolation; upgrading existing databases

**Class + learner state:** grasped/shaky, concept mastery, goals, reflections,
overlay and the existing learner-state counter. Cross-exercise pedagogy within
a class remains possible. Nothing is shared with another class, institution or
learner, even when the learner alias is identical.

**Assignment + version state:** run attempts and exercise trace events. The
store adapter translates exercise IDs to a version-specific key before writing
or counting. Customization events with an empty exercise ID belong to the class
learner. Exports include only that learner's class events and currently granted
assignment versions, and translate keys back to the learner/exercise aliases.

Physical participant/state/event keys are domain-separated SHA-256 digests of
`[namespace, institution, class, learner]`; exercise keys are digests of
`[namespace, exercise, version]`. Participant `anon_code` uses a separate
class-specific digest. The current SQL columns already fit these keys, so
**no SQL schema migration is required**. Deployment is repeatable: back up the
database, deploy this code and the protected auth files, then register each
trusted class learner. Repeated deployment/registration does not copy or relabel
legacy records. **Legacy unscoped rows are inaccessible to the new HTTP paths.**
There is no fallback to old IDs, guessed class, wildcard scope, or automatic
backfill. Retain legacy records under existing restricted retention controls;
any later recovery requires an audited, explicit ownership mapping and a
separately reviewed migration. Offline store tools operate on physical keys and
remain trusted operator tools, never exposed as HTTP bulk export.

Sidecar event/mode/stance use the same closed vocabularies as `/api` so arbitrary
text cannot be placed in trace metadata. The eight-field event row remains unchanged. At the HTTP persistence boundary,
`payload` now contains allowlisted numeric/boolean `metrics` and the authorized
`exercise_version` (null for class events). Source, stdout, dialogue, free-text
goals/reflections, notes and arbitrary model/result fields are excluded from the
trace and export. Private goals/reflections remain in scoped learner state for
tutoring. Historical/offline core traces have the old payload shape; analysis
consumers must account for this HTTP minimization rather than assume full-text
revision measures remain available. The grades firewall, governance and distress
floors are unchanged. No conversation persistence, queue, budget or B1–B4 work
is included.

## Host integration and verification

See `frontend/README.md` for in-memory credential wiring. Use short-lived tokens,
never query strings, localStorage, logs or model credentials. The browser helper
refuses to send credentials to an origin other than the host's explicit backend
origin, and allows HTTP only for loopback demos. CORS origins must match the host.

The tests generate an ephemeral RSA key and use real local signature checks,
in-memory stores or a temporary SQLite database, plus stub pack execution/control
turns. No real identity service, credentials or model is contacted:

```bash
cd backend
python -m pytest -o addopts='' -q tests/test_auth_isolation.py
ruff check .
ruff format --check .
mypy
python -m pytest -o addopts='' -q
```

Run the independent browser-helper test with `node frontend/tests/auth-client.test.cjs`.

Verifier API reference: [PyJWT decode contract](https://pyjwt.readthedocs.io/en/stable/api.html#jwt.decode).
The required-claim list and fixed algorithm are deliberate: verification of optional
claims alone does not require their presence.

## Changed-file inventory

- Identity/storage: `backend/app/auth.py`, `backend/app/store/scoped.py`,
  `backend/app/store/consent.py`, `backend/app/config.py`, `backend/requirements.txt`.
- HTTP boundaries: `backend/app/main.py`, `backend/app/schemas.py`,
  `backend/app/integrations/quad/router.py`, `backend/app/integrations/quad/schemas.py`.
- Tests: `backend/conftest.py`, `backend/tests/__init__.py`,
  `backend/tests/http_auth.py`, `backend/tests/test_auth_isolation.py`,
  `backend/tests/test_deploy.py`, `backend/tests/test_distress.py`,
  `backend/tests/test_goals.py`, `backend/tests/test_overlay.py`,
  `backend/tests/test_quad_sidecar.py`, `frontend/tests/auth-client.test.cjs`.
- Frontend requests: `frontend/auth-client.js`, `frontend/api-client.js`,
  `frontend/dev-client.html`, `frontend/embed-demo.html`, `frontend/widget.html`.
- Deployment/docs: `.env.example`, `.gitignore`, `docker-compose.yml`,
  `README.md`, `ARCHITECTURE.md`, `PRIVACY.md`, `VALIDATION.md`,
  `frontend/README.md`, `docs/authentication.md`.
