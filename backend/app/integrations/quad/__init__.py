"""Quad tutor-seam sidecar (Apache-2.0; imports core only)."""
from .router import PROTOCOL_VERSION, build_router, default_router

__all__ = ["build_router", "default_router", "PROTOCOL_VERSION"]
