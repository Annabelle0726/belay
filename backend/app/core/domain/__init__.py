"""Core domain seam — protocols, value types, and the active-pack registry."""

from .pack import DomainPack, KnowledgeBase, MisconceptionLibrary
from .registry import (
    active_pack_id,
    get_active_pack,
    register_pack,
)
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
    # registry
    "get_active_pack",
    "active_pack_id",
    "register_pack",
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
