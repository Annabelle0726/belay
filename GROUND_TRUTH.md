# GROUND_TRUTH — read-only audit of peer-tutor-framework

Read-only ground-truth audit. Every existence/location claim is backed by pasted raw
command output. "ABSENT" means the command returned nothing. Nothing was changed except
this file. No inference, no reconstruction, no fixes.

---

## Section A — file inventory (raw)

```
$ find . -type f \( -name "*.md" -o -name "DCO" \) -not -path "*/.venv/*" -not -path "*/.pytest_cache/*" | sort
./CODE_OF_CONDUCT.md
./CONTRIBUTING.md
./DCO
./LICENSING.md
./README.md
./STATE_AUDIT_DOMAIN.md
./VALIDATION.md
./backend/app/analysis/process_measures.md
./backend/app/packs/datascience/knowledge/README.md
./backend/app/packs/datascience/specs/GRADING_SPEC.md
./backend/scripts/smoke_sql_http.md
./frontend/README.md
./process_measures.md
```

Present/ABSENT per cited file (raw `find -name <f>`):
```
PRESENT  README.md            ->  ./README.md  (also ./frontend/README.md, ./backend/app/packs/datascience/knowledge/README.md)
PRESENT  VALIDATION.md        ->  ./VALIDATION.md
PRESENT  LICENSING.md         ->  ./LICENSING.md
PRESENT  CONTRIBUTING.md      ->  ./CONTRIBUTING.md
PRESENT  CODE_OF_CONDUCT.md   ->  ./CODE_OF_CONDUCT.md
PRESENT  DCO                  ->  ./DCO
ABSENT   PRIVACY.md
ABSENT   EXTRACTION_PLAN.md
ABSENT   ROADMAP.md
ABSENT   ARCHITECTURE.md
ABSENT   PROVENANCE.md
ABSENT   quad-tutor-protocol.md
```

---

## Section B — decision-record map (raw grep per record)

### B.1 Distress-response (five safe defaults; routing layer)
Earlier claim: PRIVACY.md:99 and EXTRACTION_PLAN.md:444 — **both files ABSENT (Section A)**.
Actual location: VALIDATION.md:719-770 (Slice G) + code (`agent/distress.py`).
```
$ git grep -niE "distress.?routing|DISTRESS_ROUTING_ENABLED|safe generic frame" -- '*.md'
VALIDATION.md:719:## Slice G — distress-routing layer of the wellbeing floor (safety-critical)
VALIDATION.md:731:- **OFF by default.** `DISTRESS_ROUTING_ENABLED=false` ⇒ no detection runs, no
VALIDATION.md:741:  unconfigured ⇒ a **safe generic frame** (no placeholder) + an operator config warning
VALIDATION.md:751:| `DISTRESS_ROUTING_ENABLED` | `false` | institution | master switch; off ⇒ byte-identical |
VALIDATION.md:763:with a content-free event; enabled+unconfigured safe generic frame with **no `[FILL-IN]`
VALIDATION.md:805:- **Distress startup warning:** when `DISTRESS_ROUTING_ENABLED=true` but support/
```
The five env-var safe defaults are the table at VALIDATION.md:751-755
(DISTRESS_ROUTING_ENABLED, DISTRESS_SUPPORT_MESSAGE, DISTRESS_ESCALATION_TARGET,
DISTRESS_TRACE_ENABLED, DISTRESS_SIGNAL_TERMS); the two standing IRB items at
VALIDATION.md:757-759. RECONCILE: MISLOCATED — cited files do not exist; record is in
VALIDATION.md + code.

### B.2 Leak-over-retrieval contract
Earlier claim: EXTRACTION_PLAN.md:334 — **ABSENT**. Actual: VALIDATION.md:675-712 (Slice F)
+ `core/domain/pack.py` (`KnowledgeBase` docstring).
```
$ git grep -niE "leak.?over.?retrieval|screen.*passage" -- '*.md'
VALIDATION.md:675:## Slice F — first real KnowledgeBase + leak-over-retrieval gate (safety-critical)
VALIDATION.md:691:- **The gate** (`agent/governance.screen_passages`): the decision is core's, the
VALIDATION.md:706:corpus discloses no solution; the **leak-over-retrieval block** (a solution-bearing
backend/app/packs/datascience/knowledge/README.md:16:  through the deterministic core governance leak gate (`governance.screen_passages`,
backend/app/packs/datascience/knowledge/README.md:19:  leak-over-retrieval contract at `core/domain/pack.py` (the `KnowledgeBase` docstring).
```
RECONCILE: MISLOCATED — content real, in VALIDATION.md + code, not EXTRACTION_PLAN.md.

### B.3 §6 trace schema + pack-result envelope
Earlier claim: EXTRACTION_PLAN.md schema note — **ABSENT**. Actual: VALIDATION.md:101-106
+ `backend/app/core/domain/types.py:158-182` (RunResult).
```
$ git grep -niE "schema v6|pack-agnostic envelope|RunResult|result/telemetry envelope" -- '*.md' (excerpt)
VALIDATION.md:38:builders. The §6 result/telemetry envelope was generalized (schema **v6**).
VALIDATION.md:101:**§6 result genericization (finished):** top-level `payload.result` is now
$ git grep -niE "pack-agnostic envelope|RunResult" -- backend/app/core/domain/types.py
backend/app/core/domain/types.py:158:# ── Run result (pack-agnostic envelope) ─────────
backend/app/core/domain/types.py:161:class RunResult(TypedDict, total=False):
```
RunResult top level = {ok, goalMet, metric, error, pack} (types.py:178-182).
RECONCILE: MISLOCATED — content real, in VALIDATION.md + code.

### B.4 Privacy-by-architecture (no PII, pseudonymous ids only)
Earlier claim: PRIVACY.md — **ABSENT**. Actual: README.md:28-30, CONTRIBUTING.md:15,18,
VALIDATION.md:316-329.
```
$ git grep -niE "pseudonymous|no PII|PII is rejected|never surfaced to" -- '*.md' (excerpt)
CONTRIBUTING.md:15:Sol stores pseudonymous identifiers only. It never stores or transmits student personal information.
README.md:28:- Privacy by architecture. Identity is a pseudonymous host id only (for example
README.md:29:  `gh:12345`); PII is rejected at the sidecar boundary; there is no write path to
VALIDATION.md:316:- **Pseudonymous identity only:** `pseudo_id` = host numeric user id namespaced by
VALIDATION.md:317:  provider (`gh:12345`), which IS the participant anon-code namespace. **PII is
```
RECONCILE: MISLOCATED — content real, spread across README/CONTRIBUTING/VALIDATION; no PRIVACY.md.

### B.5 Roadmap / deferred edges (cohort, facilitator-bench, containerized runner, strong-judge)
Earlier claim: ROADMAP.md — **ABSENT**. Actual: scattered mentions only; no consolidated record.
```
$ git grep -niE "facilitator|containeriz|strong.judge|cohort|roadmap" -- '*.md' (excerpt)
README.md:127:the strong-judge run at higher repeats is pending.
VALIDATION.md:79:  point and closing roadmap step is a **containerized runner** (matching Quad's
VALIDATION.md:358:- **A SEPARATE strong judge** for the qualitative rubrics (`grounded`, `concrete`,
VALIDATION.md:373:(`@family(name, category)`); the Phase 5 **facilitator** family slots in here and
VALIDATION.md:374:is documented as pending.
process_measures.md:210:- `measures_by_attempt.{jsonl}` — one row ... + `stance` + `cohort` + ...
```
`cohort` appears only as a measures output column, not a roadmap edge. RECONCILE: ABSENT as a
consolidated record — no ROADMAP.md; edges are scattered.

### B.6 Extraction phase records (Phase 0 through 1d)
Earlier claim: EXTRACTION_PLAN.md — **ABSENT**. Actual: intact in VALIDATION.md:14-144.
```
$ git grep -niE "Extraction status \(Phase" -- '*.md'
VALIDATION.md:14:## Extraction status (Phase 0)
VALIDATION.md:29:## Extraction status (Phase 1a) — core domain seam
VALIDATION.md:56:## Extraction status (Phase 1b) — data-science pack + runner (quantum still active)
VALIDATION.md:110:## Extraction status (Phase 1c) — data-science is now the active pack
VALIDATION.md:144:## Extraction status (Phase 1d) — quantum removed
```
RECONCILE: MISLOCATED — phase narrative in VALIDATION.md; named EXTRACTION_PLAN.md (with
§(c)/(d)/(g) sub-sections) does not exist.

### B.7 Licensing split (AGPL core / Apache contract)
Earlier claim: LICENSING.md present — **PRESENT and matches**.
```
$ grep -niE "AGPL|Apache|contract|copyleft" LICENSING.md (excerpt)
LICENSING.md:9:The portability contract is Apache-2.0. ... without taking on copyleft.
LICENSING.md:11:The Sol implementation is AGPL-3.0. The running tutor, its governance gate, and its reference pack are copyleft ...
LICENSING.md:19:Apache-2.0, the contract only, realized in `backend/app/core/domain/`:
LICENSING.md:24:AGPL-3.0, everything that implements the contract:
```
RECONCILE: CONFIRMED.

---

## Section C — safety-test verification (raw grep, then run)

grep -n of each named test (all PRESENT):
```
tests/test_knowledge.py:185:def test_screen_drops_solution_bearing_passage_keeps_benign():
tests/test_knowledge.py:200:def test_leak_over_retrieval_blocks_end_to_end(monkeypatch):
tests/test_goal_safety.py:110:def test_student_rule_cannot_leak():
tests/test_distress.py:146:def test_enabled_configured_routes_and_suppresses(monkeypatch):
tests/test_distress.py:166:def test_enabled_unconfigured_safe_generic_no_fillin(monkeypatch, caplog):
tests/test_distress.py:185:def test_negative_control_academic_despair_does_not_route(monkeypatch):
tests/test_distress.py:247:def test_no_verbatim_distress_text_or_pii_in_trace(monkeypatch):
tests/test_distress.py:302:def test_trace_disabled_writes_no_distress_event(monkeypatch):
tests/test_distress.py:273:def test_startup_warning_fires_only_when_enabled_and_unconfigured(monkeypatch, caplog):
tests/test_worked_example.py:32:def test_ds_claim_check_is_inert_with_expected_dist():
tests/test_import_boundaries.py:131:def test_contract_imports_nothing_app_internal():
tests/test_import_boundaries.py:66:def test_no_classiq_imports_in_core_or_packs():
tests/test_import_boundaries.py:76:def test_core_does_not_import_quantum():
```
ABSENT: none.

Run result (raw, `pytest` over the 13 node ids):
```
collected 13 items
tests/test_knowledge.py ..                                               [ 15%]
tests/test_goal_safety.py .                                              [ 23%]
tests/test_distress.py ......                                            [ 69%]
tests/test_worked_example.py .                                           [ 76%]
tests/test_import_boundaries.py ...                                      [100%]
============================== 13 passed in 1.32s ==============================
```
All 13 named safety tests PRESENT and PASS.

---

## Section D — commit-history reconciliation (raw)

`git log --oneline` (recent + first):
```
3e22d2f docs(validation): record the Slice M realization ... (Slice M Step 6)
8c9b0c7 docs(provenance): reframe provenance concept-first ... (Slice M Step 4)
e286fa5 docs(links): remove dangling docs/*.md references ... (Slice M Step 3)
b00d49e chore(docs): branch baseline — record Slice M floor (338/1) ... (Slice M Step 1)
e77e053 docs(claimcheck): record the Slice L characterization ... (Slice L Step 6)
120a92b docs(claimcheck): document the deferred, inert DS claim-check (Slice L Step 4)
3253b21 test(claimcheck): characterize the inert DS worked-example claim-check (Slice L Step 2)
ddee02a chore(claimcheck): branch baseline — record Slice L floor (337/1) ... (Slice L Step 1)
346e548 docs(debrand): record the Slice K realization ... (Slice K Step 6)
7c9f4ec refactor(debrand): generalize the spec doc, archive script, and smoke scripts (Slice K Step 3d)
2d45265 refactor(debrand): de-brand the front-end demos (Slice K Step 3c)
88f1d0a refactor(debrand): de-brand quantum vocabulary in the test suite (Slice K Step 3b)
ccb2edc refactor(debrand): generalize quantum-era residue in backend code comments (Slice K Step 3a)
a4a45aa chore(debrand): branch baseline — record Slice K floor (337/1) ... (Slice K Step 1)
6421db4 docs(license): name the realized boundary path ... (Slice J Step 7)
9f6b530 chore(license): per-file SPDX headers ... (Slice J Step 6)
2effce2 test(license): tripwire — the Apache contract (core/domain) imports nothing app-internal (Slice J Step 5)
6e23d69 refactor(license): isolate Apache contract; move active-pack registry to AGPL side (Slice J Step 3)
... (Slices I/H/G/F/D etc.) ...
7cd6b11 chore(repo): extract framework from quantum-inventioneers at 9b19cd5   (first commit)
```

Cited commits confirmed (`git cat-file -t`):
```
PRESENT  7cd6b11  chore(repo): extract framework from quantum-inventioneers at 9b19cd5
PRESENT  6421db4  Slice J Step 7   (+ 9f6b530, 2effce2, 6e23d69)
PRESENT  346e548  Slice K Step 6   (+ 7c9f4ec, 2d45265, 88f1d0a, ccb2edc, a4a45aa)
PRESENT  e77e053  Slice L Step 6   (+ 120a92b, 3253b21, ddee02a)
PRESENT  3e22d2f  Slice M Step 6   (+ 8c9b0c7, e286fa5, b00d49e)
```
No cited commit is ABSENT.

Lifecycle of the now-absent docs (`git log --diff-filter=AD --name-status`):
```
e7bbbdb docs: clean up repo + add LICENSING.md, CODE_OF_CONDUCT, CONTRIBUTING
  D docs/ARCHITECTURE.md  D docs/EXTRACTION_PLAN.md  D docs/PRIVACY.md
  D docs/PROVENANCE.md    D docs/ROADMAP.md          D docs/quad-tutor-protocol.md
f0b18f5 chore(docs): remove stale quantum-origin docs, fix dangling refs ...
  D ARCHITECTURE.md
b97a08d docs: write framework documentation set (README, ARCHITECTURE, PRIVACY, ROADMAP) ...
  A docs/ARCHITECTURE.md  A docs/PRIVACY.md  A docs/ROADMAP.md
7f1ec07 feat(quad): /quad/v1 tutor-seam sidecar ...
  A docs/quad-tutor-protocol.md
7cd6b11 chore(repo): extract framework from quantum-inventioneers at 9b19cd5
  A ARCHITECTURE.md  A docs/EXTRACTION_PLAN.md  A docs/PROVENANCE.md
```
The six docs were real in early commits and DELETED at f0b18f5 / e7bbbdb. They are genuinely
gone, not mis-pathed.

---

## Section E — synthesis

### Reconciliation table
| Item | Reported location | Ground truth | Note |
|---|---|---|---|
| README.md | present | PRESENT `./README.md` | — |
| VALIDATION.md | present | PRESENT `./VALIDATION.md` | de-facto home of nearly every decision record |
| LICENSING.md | present | PRESENT `LICENSING.md:5-34` | AGPL/Apache split confirmed |
| CONTRIBUTING / CODE_OF_CONDUCT / DCO | present | PRESENT (root) | — |
| PRIVACY.md | PRIVACY.md | ABSENT (deleted e7bbbdb) | content in README:28-30, CONTRIBUTING:15, VALIDATION:316-329 |
| EXTRACTION_PLAN.md | :334/:444 + schema note | ABSENT (deleted e7bbbdb) | phases in VALIDATION:14-144; schema in VALIDATION:101 + types.py:161 |
| ROADMAP.md | ROADMAP.md | ABSENT (deleted e7bbbdb) | edges scattered in VALIDATION (79,358,373); not consolidated |
| ARCHITECTURE.md | ARCHITECTURE.md | ABSENT (deleted f0b18f5/e7bbbdb) | governance/loop in README:14-33 + VALIDATION |
| PROVENANCE.md | PROVENANCE.md | ABSENT (deleted e7bbbdb) | origin line reframed into README:17-20 (Slice M) |
| quad-tutor-protocol.md | quad-tutor-protocol.md | ABSENT (deleted e7bbbdb) | quad posture in VALIDATION + code |
| Distress decision (5 defaults) | PRIVACY.md:99, EXTRACTION_PLAN.md:444 | VALIDATION.md:719-770 + agent/distress.py | cited files do not exist |
| Leak-over-retrieval | EXTRACTION_PLAN.md:334 | VALIDATION.md:675-712 + core/domain/pack.py | cited file does not exist |
| §6 schema/envelope | EXTRACTION_PLAN.md schema note | VALIDATION.md:101 + types.py:158-182 | cited file does not exist |
| Privacy-by-architecture | PRIVACY.md | README:28-30 + CONTRIBUTING:15 + VALIDATION:316-329 | cited file does not exist |
| Extraction phases | EXTRACTION_PLAN.md | VALIDATION.md:14-144 | intact |
| Licensing split | LICENSING.md | LICENSING.md:5-34 | confirmed |
| 13 safety tests | named files | all PRESENT + PASS | — |
| Commits 7cd6b11 / J / K / L / M | as cited | all PRESENT | — |

### Real vs. asserted
- REAL: README, VALIDATION, LICENSING, CONTRIBUTING, CODE_OF_CONDUCT, DCO; all 13 named
  safety tests (present and passing); every cited commit including extraction `7cd6b11`;
  the licensing split; the extraction phase records and the leak-over-retrieval, distress,
  and §6-schema decision content (in VALIDATION.md and code).
- ASSERTED BUT NOT IN THE REPO AS NAMED: PRIVACY.md, EXTRACTION_PLAN.md, ROADMAP.md,
  ARCHITECTURE.md, PROVENANCE.md, quad-tutor-protocol.md — all six created in early commits
  and deleted at f0b18f5/e7bbbdb; they do not exist now. Every prior citation to a specific
  line in one of these files (e.g. PRIVACY.md:99, EXTRACTION_PLAN.md:334/444) is unbacked.
  The content survives only where independently written into VALIDATION.md, README.md,
  CONTRIBUTING.md, or code docstrings.

### Needs creating or consolidating before IRB / publish
1. PRIVACY.md (create or consolidate) — privacy-by-architecture is real but scattered.
   HIGHEST PRIORITY: the distress-response decision, its five safe defaults, and the two
   standing IRB items live only in VALIDATION.md:719-770 (a dev runbook); IRB needs these
   as a first-class safety/privacy record.
2. ROADMAP.md (create or consolidate) — deferred edges (containerized runner,
   facilitator-bench, strong-judge run, cohort analysis) exist only as scattered VALIDATION
   lines; collect into one record.
3. ARCHITECTURE.md (create or consolidate) — governance/loop architecture is in README +
   VALIDATION; the standalone doc was referenced but deleted.
4. quad-tutor-protocol.md (create or consolidate) — embed/registry/FERPA protocol is
   referenced from code comments (integrations/quad/router.py:8, docker-compose.yml:9) that
   still point at the missing file.
5. PROVENANCE — already folded into README:17-20 (Slice M); no separate file needed unless
   publish wants one.
6. EXTRACTION_PLAN.md — historical; phase narrative lives in VALIDATION.md:14-144; no need
   to recreate, but the dangling agent/goals.py:36 code comment still names it.
7. Most economical path: consolidate (2)/(3) into VALIDATION.md sections and create a real
   PRIVACY.md for the IRB-facing safety+privacy record, then fix the four remaining
   code/config comments that still name deleted docs (goals.py:36, router.py:8,
   store/models.py:11, docker-compose.yml:9).
