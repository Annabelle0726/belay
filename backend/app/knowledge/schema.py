# SPDX-License-Identifier: AGPL-3.0-only
"""Passage schema and the license whitelist (the ingestion contract).

A corpus passage record is the normalized, durable unit the ingestion pipeline writes and
the indexing step reads. It records, per passage, where it came from and under what license
so attribution can travel with the passage end to end and so the license gate can refuse
anything that is not redistributable.

The license gate is non-negotiable: ingestion admits ONLY openly-licensed or public-domain
material on the whitelist below and rejects everything else with a logged reason. Copyleft
and restricted licenses (share-alike, non-commercial, no-derivatives, GPL/AGPL) are excluded
by default; including any of them is a deliberate decision that must be made explicitly, not
by accident of ingestion.
"""

from __future__ import annotations

from typing import TypedDict


class CorpusPassage(TypedDict, total=False):
    """One normalized corpus passage.

    - ``id``          stable passage id (used in the retrieval trace / drop records)
    - ``pack``        the owning pack id (the corpus is pack-scoped)
    - ``source``      provenance: the work the passage came from
    - ``license``     SPDX-style license id; MUST be on the whitelist to be ingested
    - ``attribution`` the credit line to surface with the passage (CC-BY etc. require it)
    - ``tags``        free-text tags (module / concept / topic) for context, not ranked
    - ``text``        the passage prose (the only field ranked by the index)
    """

    id: str
    pack: str
    source: str
    license: str
    attribution: str
    tags: list[str]
    text: str


# ── license whitelist (the only licenses ingestion will admit) ───────────────
#
# Whitelisted FAMILIES (redistributable, attribution-only or permissive):
#   public-domain, CC0, CC-BY (any version), MIT, Apache-2.0, BSD (2-/3-clause).
# Recorded for documentation; matching is done by `is_allowed_license` (family-aware),
# because a raw id carries a version (e.g. "CC-BY-4.0") and must be matched as a family.
LICENSE_WHITELIST: frozenset[str] = frozenset(
    {
        "PUBLIC-DOMAIN",
        "CC0",
        "CC-BY",
        "MIT",
        "APACHE-2.0",
        "BSD",
    }
)

# Markers that DISQUALIFY a license even if it otherwise looks whitelisted. Checked FIRST,
# so "CC-BY-SA-4.0" (share-alike) and "CC-BY-NC" (non-commercial) are rejected even though
# they contain "CC-BY". "GPL" also catches "AGPL"/"LGPL".
_EXCLUDED_MARKERS: tuple[str, ...] = (
    "-SA",
    "SHAREALIKE",
    "SHARE-ALIKE",
    "-NC",
    "NONCOMMERCIAL",
    "NON-COMMERCIAL",
    "-ND",
    "NODERIV",
    "NO-DERIV",
    "GPL",  # also AGPL / LGPL
)

# Allowed family prefixes/exacts, normalized (uppercased, spaces -> hyphens).
_ALLOWED_FAMILIES: tuple[str, ...] = (
    "PUBLIC-DOMAIN",
    "PUBLICDOMAIN",
    "CC0",
    "CC-BY",  # CC-BY, CC-BY-4.0, CC-BY-3.0, ... (SA/NC/ND already excluded above)
    "MIT",
    "APACHE-2.0",
    "APACHE",
    "BSD",  # BSD-2-CLAUSE, BSD-3-CLAUSE
)


def _normalize(raw: str) -> str:
    return (raw or "").strip().upper().replace(" ", "-").replace("_", "-")


def is_allowed_license(raw: str) -> bool:
    """True iff ``raw`` is on the whitelist (family-aware) and carries no excluded marker.

    Excluded markers are checked first, so any share-alike / non-commercial / no-derivatives
    / GPL variant is rejected even when it shares a prefix with an allowed family."""
    norm = _normalize(raw)
    if not norm:
        return False
    if any(m in norm for m in _EXCLUDED_MARKERS):
        return False
    return any(
        norm == fam or norm.startswith(fam + "-") or norm == fam for fam in _ALLOWED_FAMILIES
    )


def license_reason(raw: str) -> str | None:
    """Return None if the license is admissible, else a human-readable rejection reason."""
    norm = _normalize(raw)
    if not norm:
        return "missing license"
    for m in _EXCLUDED_MARKERS:
        if m in norm:
            return f"excluded license marker {m!r} (copyleft / restricted): {raw!r}"
    if not is_allowed_license(raw):
        return f"license not on whitelist: {raw!r}"
    return None


_REQUIRED_FIELDS = ("id", "pack", "source", "license", "attribution", "text")


def validate_record(rec: CorpusPassage) -> str | None:
    """Return None if ``rec`` is a complete, ingestible record, else a reason string.
    A complete record has every required field non-empty and an admissible license."""
    for f in _REQUIRED_FIELDS:
        val = rec.get(f)
        empty = val is None or (isinstance(val, str) and not val.strip())
        if empty:
            return f"missing required field {f!r}"
    return license_reason(rec.get("license", ""))
