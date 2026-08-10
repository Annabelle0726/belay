# Contributing to Sol

Sol is a domain-agnostic, evaluation-first peer tutor built as personal-time, commons-oriented work. Contributions are welcome. A few norms are load-bearing rather than stylistic, so please read these before opening a pull request.

## Sign-off: DCO, not a CLA

Every commit must carry a `Signed-off-by` line, added with `git commit -s`. By signing off you certify the Developer Certificate of Origin (the `DCO` file in this repository). There is no copyright assignment and no contributor license agreement. This keeps the project un-relicensable by any single entity.

## Licensing of contributions

Sol is dual-licensed. Contributions to the pack and runner contract are Apache-2.0; contributions to everything else are AGPL-3.0. The boundary is in `LICENSING.md`. Match the license of the file you are editing, and keep its SPDX header intact.

## Privacy is enforced in code, not by policy

Sol stores pseudonymous identifiers only. It never stores or transmits student personal information.

- Do not add code that collects, stores, or sends PII.
- The trace records pseudonymous ids and structured, content-free events. Do not add verbatim learner text to the trace, the logs, or any export.
- The distress path stores no verbatim distressing content and no category. Keep it that way.

A pull request that weakens these guarantees will be declined regardless of what else it does.

## The governance gate is safety-critical

The leak, wellbeing, and distress gates are the parts of Sol most likely to cause harm if they regress.

- Changes that touch governance need the gate tests and a clear rationale.
- The leak gate must stay deterministic and in core; packs supply evidence, not the decision.
- The distress detector vocabulary is an IRB-owned safety knob. Do not widen it casually. The negative-control test that keeps academic frustration from routing is a guard, not an obstacle.

## Development workflow

- Set up: a virtual environment plus `requirements.txt`, `requirements-dev.txt`, and `requirements-packs.txt`.
- Tests: the suite must stay green. New behavior ships with hermetic tests, meaning no network, model endpoint, or secrets.
- Quality gate: `ruff check`, `ruff format --check`, and `mypy` must pass. Run them locally before pushing; CI runs them too.
- Trace: new event types are additive. The trace row keeps its fixed field set; add information inside the payload, not by changing the row.
- Commits: conventional commit messages, one logical change per commit, docs updated in the same commit as the code they describe.

## Adding a domain

New domains go behind the `DomainPack` contract as a pack, not by editing the core. A pack supplies its taxonomy, exercises, runner behavior, leak evidence, and optionally a knowledge base. If you find yourself needing to change the core to add a domain, that is a sign the contract needs discussion first; open an issue before the pull request.

## Maintainer contact

[FILL-IN: maintainer contact for security and conduct reports]
