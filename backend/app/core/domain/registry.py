"""
Active-pack registry/loader.

Selects the active `DomainPack` from configuration (``TUTOR_PACK``, default
``datascience``). The concrete pack is imported lazily inside the loader so that
``core.domain`` never imports a domain at module load — keeping the dependency
arrow pointing from packs to core, not the reverse.
"""
from __future__ import annotations

import os
from typing import Callable, Dict, Optional

from .pack import DomainPack

DEFAULT_PACK = "datascience"


def _load_datascience() -> DomainPack:
    # Lazy import: avoids a core -> packs import at module load.
    from ...packs.datascience import DataSciencePack
    return DataSciencePack()


def _load_skeleton() -> DomainPack:
    from ...packs._skeleton import SkeletonPack
    return SkeletonPack()


# pack id -> zero-arg factory. New packs register here.
_FACTORIES: Dict[str, Callable[[], DomainPack]] = {
    "datascience": _load_datascience,
    "_skeleton": _load_skeleton,
}

_active: Optional[DomainPack] = None
_active_id: Optional[str] = None


def active_pack_id() -> str:
    """The configured active pack id (``TUTOR_PACK`` env, default ``datascience``)."""
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
