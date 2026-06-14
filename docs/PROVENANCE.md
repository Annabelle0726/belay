# Provenance

This repository is an extraction of a domain-agnostic, evaluation-first peer-tutor
framework from the quantum application **quantum-inventioneers**. This file is an IP
record, not narrative.

## Origin

| Field | Value |
|---|---|
| Origin repo | `quantum-inventioneers` |
| Origin path | `~/Desktop/quantum-inventioneers` (local, treated as read-only) |
| Origin commit (ORIGIN_HASH) | `9b19cd5c1a5e0331cec996ba92e903f9a6571e45` |
| Origin branch at extraction | `chore/post-feature-dial-in` (see note below) |
| Extraction date | 2026-06-14 |
| This repo's name | `peer-tutor-framework` — **placeholder**, final name pending |

**Branch note.** The brief assumed the origin would be on `main`. It was not: the
origin's de-facto integration trunk is `feat/persistent-learner-model`
(`origin/HEAD`), and `origin/main` (`f7ab84a`) is stale — it predates and omits the
persistent-learner-model feature. The extraction baseline was therefore taken at
`9b19cd5` (the trunk plus a docs-only "post-feature dial-in" commit), confirmed by
the repo owner. The origin tree was copied verbatim with `git archive HEAD` (tracked
files only; `.git`, virtualenvs, `__pycache__`, `.env`, and `*.db` are excluded by
construction). See `docs/EXTRACTION_PLAN.md` §(e) Drift for the full record.

## Name

The final framework name is **pending**. `peer-tutor-framework` is a working
placeholder. The rename to the final name will be a single atomic commit before any
public release (the obvious candidates require a real domain/org/package
availability check first).

## Status

- The framework **core** is developed on personal time and is intended for
  **open-source** release.
- To satisfy the Quad/EduCloud integration boundary, the framework core and the
  Quad integration layer are intended to stay **Apache-2.0-compatible**, importing
  only from the framework core (never from any AGPL-3.0 control plane). See
  `docs/EXTRACTION_PLAN.md` for the Quad constraint set this honors.

## IP boundary

The following remain **in the origin repository** and are **not** part of this
framework:

- **Classiq** SDK usage, configuration, and the Classiq quantum backend.
- The **TLA** / quantum-specific intellectual property.
- The **quantum application** itself: the ≤4-qubit simulator, the functional-model
  compiler, the quantum grader/leak-oracle, the quantum curriculum, and the "Sol"
  quantum-peer persona.

What is extracted here is the **domain-agnostic, evaluation-first peer-tutor**: the
five-component agent loop (Planner · Peer-Reasoner · Self-Evaluation · bounded
refine · deterministic Governance · Memory), the §6 trace schema and its export
contract, the consent-gated store, and the measures/eval harness — with the quantum
domain to be removed and replaced by pluggable packs in later phases.

> Phase 0 is extraction baseline only: copy, map, document. No origin code has been
> deleted or refactored here; the copied app is still the quantum app. Deletions and
> the core/pack split happen in Phase 1, per `docs/EXTRACTION_PLAN.md`.
