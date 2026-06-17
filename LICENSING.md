# Licensing

Status: prepared, not yet in force. Sol is published, and these licenses take effect, only once the University of Arizona IP release for the personal-time work has cleared. Until then this file is a plan, not a grant.

## The split, and why

Sol uses two licenses on purpose.

The portability contract is Apache-2.0. Anyone should be able to write a pack, an alternative runner, or a different tutor against the same interfaces without taking on copyleft. Making the contract permissive maximizes reuse, which is the point of a contract.

The Sol implementation is AGPL-3.0. The running tutor, its governance gate, and its reference pack are copyleft so that improvements to a deployed service flow back to the commons, including over a network.

This is the same principle Cairn uses: the interoperability primitives are Apache, the platform that implements them is AGPL.

## Confirmed boundary (realized in code; the grant is not yet in force)

This boundary is confirmed and now realized in the source tree as a single-license directory plus per-file SPDX headers. The realization changed no runtime behavior; only the license *grant* waits on the IP release (see Status above).

Apache-2.0, the contract only, realized in `backend/app/core/domain/`:

- The `DomainPack`, `KnowledgeBase`, and `MisconceptionLibrary` protocols (`core/domain/pack.py`) and the value types that define them (`core/domain/types.py`: `PersonaSpec`, `Concept`, `Taxonomy`, `Exercise`, `Module`, `RunResult`, `WorkedExample`, `VerifyResult`, `LeakEvidence`, `Passage`).
- `core/domain/` is exactly the contract and nothing more: it imports nothing app-internal (only stdlib + typing + its own intra-contract modules), so the Apache surface is the base of the dependency graph. An import-boundary tripwire (`tests/test_import_boundaries.py::test_contract_imports_nothing_app_internal`) fails the build if any implementation leaks back into it.

AGPL-3.0, everything that implements the contract:

- The active-pack registry that selects and loads implementations (`core/registry.py`, moved out of `core/domain/` so the contract stays single-license), the Sol agent (`agent/`), the governance gate, the sandbox runner implementation (`core/runner`), the datascience pack, the store, and the integrations. The Quad sidecar at `integrations/quad/` is import-clean (it imports framework core only, never a pack), but it is an implementation and so is AGPL.

The line is exactly this: the contract is permissive, every concrete implementation is copyleft. If you want the runner interface or anything else moved across the line, say so and the files adjust.

## Placement (at publish time)

- AGPL-3.0 full text at the repository root as `LICENSE`. Drop in the verbatim text from the FSF (gnu.org); do not modify it.
- Apache-2.0 full text alongside the contract module as its `LICENSE`, or in `LICENSES/Apache-2.0.txt`. Drop in the verbatim text from apache.org; do not modify it.
- Per-file SPDX headers (`SPDX-License-Identifier: AGPL-3.0-only` or `Apache-2.0`) so the boundary is legible file by file, not just by directory. These headers are already in place on every source file; they are declarations of intent that become a grant only when the two license texts are dropped in and the Status above flips to in force.

## Contributions: DCO, not a CLA

Contributions are accepted under the Developer Certificate of Origin, with a `Signed-off-by` line on each commit. There is no copyright assignment and no contributor license agreement. This is deliberate: with no single entity holding assigned copyright, no single entity can relicense the project out from under its contributors. See `CONTRIBUTING.md` and the `DCO` file.
