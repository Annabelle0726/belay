# SPDX-License-Identifier: AGPL-3.0-only
"""
Host integrations (Apache-2.0-compatible seams).

Each integration adapts an external host (e.g. the EduCloud Quad control plane) to
the framework's existing tutor loop. INVARIANT: integrations import only the
framework CORE (`app.agent`, `app.core`, `app.store`, `app.config`, `app.schemas`)
— never `packs.*`. The active pack is resolved through the core registry at
runtime. This keeps the integration surface license-clean (Apache-2.0) and
domain-agnostic, and is enforced by tests/test_import_boundaries.py.
"""
