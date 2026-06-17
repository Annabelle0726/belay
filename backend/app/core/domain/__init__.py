# SPDX-License-Identifier: Apache-2.0
"""Core domain CONTRACT (Apache-2.0): the protocols and value types a pack/runner
must satisfy. This package is the base of the dependency graph — it imports nothing
app-internal (only stdlib + typing). The active-pack registry that SELECTS and loads
implementations lives in `core.registry` (AGPL), not here, so this directory is a
single-license (Apache) surface. See LICENSING.md."""

from .pack import DomainPack, KnowledgeBase, MisconceptionLibrary
from .types import (
    Concept,
    Exercise,
    LeakEvidence,
    Module,
    Passage,
    PersonaSpec,
    RunResult,
    Taxonomy,
    VerifyResult,
    WorkedExample,
)

__all__ = [
    # protocols
    "DomainPack",
    "KnowledgeBase",
    "MisconceptionLibrary",
    # types
    "PersonaSpec",
    "Concept",
    "Taxonomy",
    "Exercise",
    "Module",
    "RunResult",
    "WorkedExample",
    "VerifyResult",
    "LeakEvidence",
    "Passage",
]
