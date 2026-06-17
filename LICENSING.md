# Licensing

Status: prepared, not yet in force. Sol is published, and these licenses take effect, only once the University of Arizona IP release for the personal-time work has cleared. Until then this file is a plan, not a grant.

## The split, and why

Sol uses two licenses on purpose.

The portability contract is Apache-2.0. Anyone should be able to write a pack, an alternative runner, or a different tutor against the same interfaces without taking on copyleft. Making the contract permissive maximizes reuse, which is the point of a contract.

The Sol implementation is AGPL-3.0. The running tutor, its governance gate, and its reference pack are copyleft so that improvements to a deployed service flow back to the commons, including over a network.

This is the same principle Cairn uses: the interoperability primitives are Apache, the platform that implements them is AGPL.

## Proposed boundary (FLAG: confirm or redline before anything lands)

Apache-2.0, the contract only:

- The `DomainPack`, `KnowledgeBase`, and `Passage` protocols, and the value types that define them (`Taxonomy`, `RunResult`, `LeakEvidence`).
- To realize this cleanly the contract definitions should sit in their own clearly licensed module, so the Apache surface is exactly the contract and nothing more. Today they live in `core/domain`; isolating the pure protocol and type definitions there (or in a `core/domain/contract` submodule) is the small refactor this split implies.

AGPL-3.0, everything that implements the contract:

- The Sol agent (`agent/`), the governance gate, the sandbox runner implementation (`core/runner`), the datascience pack, the store, and the integrations.

The line to confirm is exactly this: the contract is permissive, every concrete implementation is copyleft. If you want the runner interface or anything else moved across the line, say so and the files adjust.

## Placement (at publish time)

- AGPL-3.0 full text at the repository root as `LICENSE`. Drop in the verbatim text from the FSF (gnu.org); do not modify it.
- Apache-2.0 full text alongside the contract module as its `LICENSE`, or in `LICENSES/Apache-2.0.txt`. Drop in the verbatim text from apache.org; do not modify it.
- Per-file SPDX headers (`SPDX-License-Identifier: AGPL-3.0-only` or `Apache-2.0`) so the boundary is legible file by file, not just by directory.

## Contributions: DCO, not a CLA

Contributions are accepted under the Developer Certificate of Origin, with a `Signed-off-by` line on each commit. There is no copyright assignment and no contributor license agreement. This is deliberate: with no single entity holding assigned copyright, no single entity can relicense the project out from under its contributors. See `CONTRIBUTING.md` and the `DCO` file.
