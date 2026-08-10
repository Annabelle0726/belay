# STATE_AUDIT_DOMAIN — where Sol is still quantum-shaped (read-only audit)

Read-only reconnaissance of `~/Desktop/peer-tutor-framework` @ branch `slice-k-debrand`.
No framework files were changed except this report. Every claim cites a file:line or
command output; unevidenced claims are marked UNKNOWN. Capability verdicts: DONE,
BROKEN, BYPASSED, QUANTUM-SHAPED.

---

## Section A — the measures layer

### A.1 Inventory of quantum-shaped elements (file:line)

- `tvd` (legacy result field, read only): `app/analysis/measures.py:13` (docstring), `:68`,
  `:70` (`res.get("tvd")`, then `res.get("pack").get("tvd")`).
- `dist` / `bits` (legacy result field, read only): `app/agent/context.py:66-69`
  (`pack_env.get("dist") or result.get("dist")`, then `f"{d['bits']}:{round(d['p']*100)}%"`).
- `tvd_slope` (aggregate OUTPUT key): `app/analysis/measures.py:287` (param), `:394`
  (computed via `_linear_slope`), `:527` (emitted in the attempt-measures dict).
- `avg_tvd_slope` (aggregate OUTPUT key): `app/analysis/measures.py:644` (cohort mean of
  per-attempt `tvd_slope`).
- The result envelope they live in: the run-event `payload["result"]` (RunResult). The
  contract is pack-agnostic — `ok, goalMet, metric, error, pack` (`app/core/domain/types.py:178-182`).
  `tvd`/`dist`/`bits` are NOT in the contract; they are pre-v6 legacy keys.
- The "calibration that consumes them": NONE. The §4a leak calibration
  (`brier_score`/`ece`, `app/analysis/measures.py`) keys off predicted-leak vs
  actual-leak and confidence, not `tvd`. `tvd`/metric feeds only the §5 struggle/progress
  measures (`_span_class`, `tvd_slope`, `repeated_error_count`: `measures.py:200-210, 244-252,
  287-295, 372-394, 433`).

Verdict: **QUANTUM-SHAPED** — but only in (a) two output key names (`tvd_slope`,
`avg_tvd_slope`) and (b) vestigial legacy reader fallbacks. See A.3.

### A.2 Producer → consumer chain

- Producer: `app/main.py:103-119` — `POST /api/run` calls `_pack.run(source, ex)` and
  writes `make_event(..., "run", {"source": ..., "result": result})`. The active pack's
  `run()` is the sole result producer.
- Consumers of the result/metric:
  - `app/analysis/measures.py:52-71` (`_metric`) reads `result["metric"]`, falling back to
    `result["tvd"]` then `result["pack"]["tvd"]`. Feeds `_metric`-based struggle measures.
  - `app/agent/context.py:58-76` builds the tutor's `last_result` view: prefers
    `result["pack"]["summary"]` (`:64-65`), falls back to legacy `dist`/`diff`/`bits`
    (`:66-69`); also passes through `result["metric"]` (`:75`).
  - `app/agent/learner_model.py:72` reads only `result["goalMet"]`/`goal_met` (no tvd/dist).
- §6 trace record: fixed 8-field row — `participant_id, ts, exercise_id, mode, event_type,
  stance, payload, note` (`app/store/models.py:100-113`; `app/store/repository.py:22-46`).
  The row shape is fixed and `event_type` is additive (`repository.py:31-33`). The result
  envelope lives inside `payload`, so its shape is not constrained by the row schema.

### A.3 How the datascience pack is fitted today — KEY QUESTION

DS does NOT shoehorn into the distribution-comparison envelope. `app/packs/datascience/grader.py:78-119`
returns the clean v6 contract: `{"ok", "goalMet", "metric": grade_obj.get("metric"), "error",
"pack": {"id":"datascience", "checks", "stdout", "summary"}}` (`:96-105`, `:110-119`). No
`tvd`/`dist`/`bits` are emitted.

Confirming no live producer emits the quantum envelope:
`git grep '"tvd"|"dist"|"bits"' -- app/` returns only READERS (`measures.py:13,68,70`;
`context.py:66-69`) and the unrelated `VerifyResult.dist` field set to `None`
(`packs/datascience/pack.py:115,118,123,135,138`; `packs/_skeleton/pack.py:107`). There is
**no live producer of `tvd`/`dist`/`bits` anywhere in the codebase**.

Verdict: DS metric/progress path is **DONE** on the clean contract; the quantum envelope is
**vestigial** (legacy-trace fallback readers + two output key names), not load-bearing.

### A.4 Domain-agnostic measure abstraction + migration surface

Abstraction (proposed, not built): the pack already supplies `goalMet` + a domain-defined
`metric` (lower-is-better progress proxy) + `pack.summary`. The clean abstraction is exactly
this contract; the only quantum residue to migrate is naming + the dead fallback.

Migration surface:
- Rename output keys `tvd_slope`→`metric_slope` (or `progress_slope`) and
  `avg_tvd_slope`, `measures.py:287,394,433,527,644` — touches eval/report consumers that
  read those keys (`evals/behavioral/*`, tests). Suite-provable.
- Drop or comment the legacy `tvd`/`dist`/`bits` fallback readers (`measures.py:66-70`,
  `context.py:66-69`) once no pre-v6 traces need parsing. Behavior-affecting only for
  pre-v6 traces.
- §6 impact: NONE structurally — the row is fixed and `event_type` additive
  (`repository.py:31-33`); the metric lives in `payload["result"]` which is already
  pack-namespaced. UNKNOWN whether any archived pre-v6 trace files still rely on the `tvd`
  fallback (no trace corpus inspected).

---

## Section B — prompt and worked-example layer (priority finding)

### B.1 Quantum-native content in prompts.py (file:line)

The persona/stance text is pack-injected and DS-framed (`packs/datascience/pack.py:35,48,55,58`
— "undergraduate data science course", "numpy/pandas", "held-out metrics"). The
quantum-native content is HARDCODED in the core reasoner bodies, prepended by
`reasoner_system()` (`prompts.py:417-420`):

- DSL op list (LIVE, model-facing): `prompts.py:131-132` — "runnable functional-model
  source (ops: allocate/superpose/entangle/flip/phase/sgate/measure)".
- "measurement distribution in `expected_dist` ({bitstring: probability})":
  `prompts.py:133-134` and the oracle copy `:192-194`.
- "the current quantum state/bug" confidence instruction: `prompts.py:139`.
- worked_example JSON schema example with bitstrings: `prompts.py:173` and `:210`
  (`{"source": "<functional-model snippet>", "expected_dist": {"<bits>": <prob>}}`).
- quantum misconception example: `prompts.py:209` ("e.g. M2.1-superpose-both-is-entangle").

Scope: the planner bodies (`prompts.py:47-110`) and self-eval bodies (`:214-271`) are clean.
Quantum framing is concentrated in `_REASONER_BODY` (`:111-176`) and `_ORACLE_REASONER_BODY`
(`:177-213`): specifically the WORKED EXAMPLE GUIDANCE, the JSON output schema, one
confidence-instruction noun ("quantum state/bug"), and the misconception example. A DS
student IS therefore addressed in quantum-flavored terms on `worked_analogy` turns (told to
write `allocate/superpose/...` source and predict a "measurement distribution"), and the
reasoner is always instructed to rate confidence in "the current quantum state/bug".

Verdict: **QUANTUM-SHAPED** (live, model-facing, both peer and oracle reasoner bodies).

### B.2 Worked-example verification path for a DS exercise — PRIORITY FINDING

End-to-end trace:
1. Reasoner is prompted to emit `worked_example = {source, expected_dist}` (`prompts.py:131-134,
   173, 210`).
2. Orchestrator dispatches on `worked_analogy`: `orchestrator.py:314-315` calls
   `pack.verify_worked_example(draft["worked_example"], exercise)` (pack = active = DS), with a
   retry loop `:317-331`.
3. DS `verify_worked_example` (`packs/datascience/pack.py:104-141`):
   - core gate: requires `source` present (`:113-115`), runs via the grader (`:116`),
     rejects non-running (`:117-118`) and rejects `goalMet` i.e. would-solve (`:119-127`).
     This is field-agnostic and FUNCTIONAL.
   - optional claim check: `expected = worked_example.get("expected_stdout")` (`:126`); only
     if `expected is not None` does it compare against `pack.stdout` (`:128-137`).
4. Field mismatch: the contract field is `WorkedExample.expected_dist`
   (`types.py:188-190`) and the prompt populates `expected_dist`. `git grep expected_stdout
   -- app/ evals/` returns ONLY the DS reader (`pack.py:111,126`); it is NEVER populated
   anywhere. `git grep expected_dist` shows it is the contract field + prompt + spec, never
   read by the verifier.

Therefore for DS: `expected = worked_example.get("expected_stdout")` is always `None`, the
`if expected is not None` branch never executes, and `claim_ok` is always `None`
(`pack.py:127,138`).

Verdict:
- DS worked-example SAFETY gate (runs + does-not-solve): **DONE** (executes, field-agnostic;
  this is what gates whether the example is shown).
- DS worked-example PREDICTION/CLAIM verification: **BYPASSED** (the prediction branch is dead
  code for DS because the prompt/contract write `expected_dist` while the verifier reads the
  never-populated `expected_stdout`). No prediction is ever verified; `claim_ok` is always
  `None`. This is a latent correctness bug, scoped to the optional claim-check, not the gate.

### B.3 Contract-vs-implementation gap

- Clean contract holds: `RunResult` (`types.py:161-182`) is pack-agnostic; DS produces it
  cleanly (`grader.py:110-119`); governance consumes `LeakEvidence` (`types.py:229-231`),
  not domain fields; learner_model reads only `goalMet` (`learner_model.py:72`).
- Quantum leaks through implementation/contract here:
  - `WorkedExample.expected_dist: dict[str,float]|None` (`types.py:190`) — the CONTRACT itself
    is quantum-shaped (a measurement distribution); the DS verifier silently expects a
    different field (`expected_stdout`).
  - measures output key names `tvd_slope`/`avg_tvd_slope` (`measures.py:527,644`).
  - reasoner prompt bodies (B.1).
  - legacy `tvd`/`dist`/`bits` fallback readers (`measures.py:66-70`, `context.py:66-69`).

---

## Section C — docs and provenance

### C.1 Doc-rot resolution

There is **no `docs/` directory** (`ls docs/ backend/docs/` → "No such file or directory").
Living doc files (actual, on disk):
- Repo root: `README.md`, `VALIDATION.md`, `LICENSING.md`, `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`, `DCO`, `process_measures.md`.
- backend: `backend/app/analysis/process_measures.md` (byte-identical duplicate of the root
  `process_measures.md`), `backend/app/packs/datascience/knowledge/README.md`,
  `backend/app/packs/datascience/specs/GRADING_SPEC.md`, `backend/scripts/smoke_sql_http.md`.
- frontend: `frontend/README.md`.
- (`backend/.pytest_cache/README.md` is tool-generated; ignore.)

Dangling references (path mentioned, file absent):
- `docs/PROVENANCE.md` — `README.md:10,19,133`; `knowledge/README.md:32`; `VALIDATION.md:914`.
- `docs/ARCHITECTURE.md` — `README.md:26`.
- `docs/PRIVACY.md` — `README.md:30`; `process_measures.md:9` (both copies);
  `backend/app/store/models.py:11`.
- `docs/EXTRACTION_PLAN.md` — `README.md:133`; `VALIDATION.md:21,39,567,602`;
  `backend/app/agent/goals.py:36`.
- `docs/ROADMAP.md` — `README.md:127`.
- `docs/quad-tutor-protocol.md` — `README.md:110`; `VALIDATION.md:312,434,653`;
  `backend/app/integrations/quad/router.py:8`; `docker-compose.yml:9`.

Canonical home: there is none today; every `docs/*.md` link is dangling. The only living
home is the repo root (top-level `.md` files) plus the duplicated `process_measures.md`.
Verdict: doc-link layer **BROKEN** (6 distinct dangling targets); content homes are root +
inline.

### C.2 Provenance / attribution references

- `README.md:18-19`: "the quantum application it was extracted from stays in its origin repo
  and is not part of this framework (`docs/PROVENANCE.md`)" — "extracted from" framing +
  dangling link.
- `README.md:10`: blockquote pointing to `docs/PROVENANCE.md`.
- `VALIDATION.md:14-16`: "Extraction status (Phase 0) … This runbook was ported from the
  origin app `quantum-inventioneers` @ `9b19cd5`"; further Extraction-status sections
  `:29,57,111,145`.
- Git history (the actual record): first commit `7cd6b11 2026-06-14 chore(repo): extract
  framework from quantum-inventioneers at 9b19cd5`; then `2088ba2` core seam, `a64254a
  feat(quantum): implement DomainPack in place`, etc. (`git log --reverse`). The repo's
  history literally begins as an extraction snapshot of the quantum tutor.

Corrected-history note (recommendation, not a change): the accurate precedence is that Sol is
an original framework whose first implementation was built inside a quantum tutor — quantum
was the substrate, not the origin. The git history is consistent with "first implementation
lived in the quantum repo" (the extraction commit), so reframing the prose from "extracted
from / the quantum application it was extracted from" to "Sol's first implementation was built
inside the Quantum Inventioneers tutor; that substrate stays in its own repo" keeps the
attribution truthful to git while removing the implication that quantum came first.
Recommendation only; no edit made.

---

## Section D — infra identifiers (`qimvp` / `qi`) rename surface

Behavior-affecting (the default DSN — changing it changes which DB a deployment uses):
- `backend/app/config.py:146` — `database_url` default `sqlite:///./qimvp.db` (the real default).
- `backend/Dockerfile:17` — `DATABASE_URL=sqlite:///./qimvp.db` (container default ENV).
- `docker-compose.yml:23` — `DATABASE_URL: ${DATABASE_URL:-sqlite:///./qimvp.db}` (compose default).
- `.env.example:49` — `DATABASE_URL=sqlite:///./qimvp.db` (documented default).

Coordinated config (Postgres opt-in; these must change together to stay consistent):
- `docker-compose.yml:41-43` — `POSTGRES_USER: qi`, `POSTGRES_PASSWORD: qi`, `POSTGRES_DB: qimvp`.
- `docker-compose.yml:45,50` — volume `qi_pgdata`.
- `docker-compose.yml:13` — comment DSN `postgresql+psycopg://qi:qi@db:5432/qimvp`.
- `.github/workflows/ci.yml:24-26` — `POSTGRES_USER/PASSWORD/DB` = `qi`/`qi`/`qimvp`.
- `.github/workflows/ci.yml:56` — `DATABASE_URL: postgresql+psycopg://qi:qi@localhost:5432/qimvp`.
- `.env.example:51` — commented `postgresql+psycopg://qi:qi@db:5432/qimvp`.

Doc/dev mentions riding the same identifiers (not infra, but reference the names):
`backend/scripts/smoke_sql.py:17,36`; `backend/scripts/smoke_sql_http.md:20`;
`backend/tests/test_sql_store.py:6` (docstrings); `VALIDATION.md:172,184-186,470,643,1003,1016,1032`;
`README.md:71`. Stale container-name example: `VALIDATION.md:1013` (`quantum-inventioneers-db-1`;
the compose project has no `name:`, so the real default is `peer-tutor-framework-db-1`).

Note for an atomic rename: the four behavior-affecting sites set the default SQLite filename
(`qimvp.db`); renaming changes the on-disk DB path for fresh deploys (existing `qimvp.db`
files would be orphaned). The Postgres credentials/DB/volume are internally consistent and
must move together with their `DATABASE_URL`s.

---

## Section E — current role and mode model

Verdict: there is **no authenticated role or mode concept** today.

- API auth: NONE. `app/main.py:55-60` registers only `CORSMiddleware`.
  `git grep 'Depends(|HTTPBearer|HTTPBasic|OAuth2|Security(' -- app/` → "NONE FOUND". All
  endpoints (`main.py:88,98,103,124,151,162,171,183,189,201`; quad router
  `integrations/quad/router.py:49`) are open.
- Student vs instructor: "instructor" appears ONLY as prompt-facing wording
  (`prompts.py:27,33,39,60`; `packs/datascience/pack.py:35,39`), an escalation flag label
  `"flag_escalate": "Flagged for instructor"` (`orchestrator.py:60`), and a documented claim
  `"instructor_surfaces": "class-level aggregates only"` (`integrations/quad/router.py:83`).
  No instructor identity, endpoint, or privileged surface is implemented.
- Identity: pseudonymous only — `participant_id` / `anon_code` / `consent` boolean, with
  consent routing storage to durable vs ephemeral (`main.py:19-25,151-159`;
  `store.ConsentRouter`). No login, no PII, no token.
- "role" in the codebase = LLM component role (planner/reasoner/self_eval), not a user role.
- "mode" = `"study"` (default, `orchestrator.py:228`; written at `main.py:116`). The only
  other mode-like construct is the pedagogical ROLE-FLIP TEACH MODE (`prompts.py:43`,
  `TEACH_ADDENDUM`, an `intervention`), which is a tutoring move, not an auth mode.
- `stance` = peer | oracle | control (`config.py:117,132`) is the research manipulation
  assigned per enrollment URL, not an authenticated capability.

Grounding for a later instructor-mode design: greenfield. No auth, session role, or
privileged surface exists to extend; an instructor mode would be net-new (identity + authz +
a gated surface), and the existing "class-level aggregates only" claim
(`router.py:83`) is currently just documentation, not enforced code.

---

## Section F — ranked plan to make Sol domain-agnostic (DO NOT START)

Ranking: (1) latent correctness bug; (2) substantive domain-agnostic work; (3) work the
stubbed suite cannot prove invariant (needs live eval); (4) cleanups.

1. **Fix the worked-example field mismatch (`expected_dist` vs `expected_stdout`).**
   Scope: reconcile `WorkedExample` contract, the reasoner prompt, and DS
   `verify_worked_example` onto one field so DS prediction-claim verification actually runs.
   Evidence: B.2 (`types.py:190`, `prompts.py:134,173,210`, `pack.py:126`; `expected_stdout`
   never populated). Size: S. Dependency: none (but interacts with item 3 since the prompt
   change is model-facing). Rationale: it is the only latent correctness bug — a dead
   verification branch shipping silently.

2. **Generalize the worked-example contract field off `expected_dist`.**
   Scope: replace the quantum-shaped `WorkedExample.expected_dist` with a pack-agnostic
   prediction field (e.g. `expected_output`) the pack interprets. Evidence: B.3
   (`types.py:190`). Size: M. Dependency: item 1 (same surface; do together). Rationale:
   substantive domain-agnostic work; the contract itself currently leaks quantum.

3. **Rename the measures output keys + retire the legacy result-envelope fallback.**
   Scope: `tvd_slope`/`avg_tvd_slope` → metric-neutral names; drop/guard the `tvd`/`dist`/`bits`
   readers once no pre-v6 traces are parsed. Evidence: A.1, A.3, A.4 (`measures.py:527,644,66-70`;
   `context.py:66-69`; no live producer). Size: M. Dependency: confirm eval/report key
   consumers (`evals/behavioral/*`, tests) and pre-v6 trace need (UNKNOWN). Rationale:
   substantive domain-agnostic work, suite-provable, but touches the report schema and
   external readers.

4. **De-quantum the live reasoner prompt bodies.**
   Scope: replace the hardcoded DSL op list, "measurement distribution"/bitstring schema, the
   "quantum state/bug" noun, and the M2.1 example in `_REASONER_BODY`/`_ORACLE_REASONER_BODY`
   with pack-supplied or neutral wording. Evidence: B.1 (`prompts.py:131-139,173,192-194,209-210`).
   Size: M. Dependency: items 1-2 (the worked-example schema in the prompt must match the new
   contract). Rationale: cannot be proven invariant by the stubbed suite (LLM calls are
   stubbed); needs the live evaluation to confirm tutor behavior is unchanged for DS.

5. **Doc-rot + provenance reframe.**
   Scope: create the missing `docs/` homes or repoint the 6 dangling targets; reframe
   "extracted from" provenance to the corrected precedence. Evidence: C.1, C.2. Size: M.
   Dependency: none. Rationale: cleanup (no runtime effect), but high reader-facing value.

6. **Atomic `qimvp`/`qi` infra rename.**
   Scope: rename the default DSN + Postgres creds/DB/volume across config, Dockerfile,
   compose, CI, .env.example, docs in one change. Evidence: Section D. Size: M (S per site;
   M to coordinate). Dependency: none. Rationale: cleanup; the default-DSN sites are
   behavior-affecting (on-disk DB path) so must move atomically and be announced.

7. **(Pre-req for a future instructor mode, not domain-agnosticism) auth/role substrate.**
   Scope: none exists (Section E). Flagged as greenfield, out of scope for domain-agnostic
   work; listed so the ranking is complete. Size: L. Dependency: product decision.

### UNKNOWNs
- Whether any archived pre-v6 trace corpus still relies on the `tvd`/`dist` fallback (no trace
  files inspected) — gates how safely item 3's fallback can be dropped.
- Exact external consumers of `tvd_slope`/`avg_tvd_slope` beyond `evals/` + tests (not
  exhaustively traced).
