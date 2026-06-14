"""
Active-pack registry/loader.

Selects the active `DomainPack` from configuration (``TUTOR_PACK``, default
``quantum``). The concrete pack is imported lazily inside the loader so that
``core.domain`` never imports a domain at module load — keeping the dependency
arrow pointing from packs to core, not the reverse.
"""
from __future__ import annotations

import os
from typing import Callable, Dict, Optional

from .pack import DomainPack

# Default pack id while quantum remains the active pack (Phase 1a).
DEFAULT_PACK = "quantum"


def _load_quantum() -> DomainPack:
    # Lazy import: avoids a core -> quantum import at module load.
    from ...quantum.pack import QuantumPack
    return QuantumPack()


# pack id -> zero-arg factory. New packs (e.g. datascience in 1b) register here.
_FACTORIES: Dict[str, Callable[[], DomainPack]] = {
    "quantum": _load_quantum,
}

_active: Optional[DomainPack] = None
_active_id: Optional[str] = None


def active_pack_id() -> str:
    """The configured active pack id (``TUTOR_PACK`` env, default ``quantum``)."""
    return os.environ.get("TUTOR_PACK", DEFAULT_PACK)


def get_active_pack() -> DomainPack:
    """Return the active `DomainPack`, constructing+caching it on first use.

    Re-reads ``TUTOR_PACK`` each call and rebuilds if it changed, so tests can
    switch packs by setting the env var.
    """
    global _active, _active_id
    pid = active_pack_id()
    if _active is None or _active_id != pid:
        try:
            factory = _FACTORIES[pid]
        except KeyError:
            raise ValueError(
                f"unknown TUTOR_PACK={pid!r}; known packs: {sorted(_FACTORIES)}"
            )
        _active = factory()
        _active_id = pid
    return _active


def register_pack(pack_id: str, factory: Callable[[], DomainPack]) -> None:
    """Register a pack factory under ``pack_id`` (used by future packs/tests)."""
    _FACTORIES[pack_id] = factory
