# SPDX-License-Identifier: AGPL-3.0-only
"""Ingestion pipeline: openly-licensed sources -> a normalized, license-gated corpus.

This is a domain-reusable tool, parameterized by pack id and sources. It hardcodes no
textbook, repository, or domain. It does ONE thing: take sources, refuse anything whose
license is not on the whitelist (logging the reason), and normalize the accepted content
into `CorpusPassage` records carrying pack, license, and attribution.

Decoupled from indexing by design: ingestion writes the normalized corpus artifact and
nothing else. Building a searchable index over the corpus is a SEPARATE step (`index` /
`corpus_kb`), so the retrieval method stays swappable behind the contract without re-ingest.

A "source" is a plain dict::

    {
      "source": "<provenance, e.g. work title>",   # required
      "license": "<license id, e.g. CC-BY-4.0>",    # required; gated against the whitelist
      "attribution": "<credit line to surface>",    # required (CC-BY etc. require it)
      "tags": ["topic", ...],                        # optional, source-level
      "passages": [ {"id": "...", "text": "...", "tags": [...]}, ... ],
    }
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass

from .schema import CorpusPassage, license_reason, validate_record

log = logging.getLogger("peer_tutor.knowledge.ingest")


@dataclass(frozen=True)
class RejectedSource:
    """A source (or passage) that ingestion refused, with the reason it was logged under."""

    source: str
    license: str
    reason: str


def ingest(
    pack_id: str,
    sources: Iterable[dict],
    *,
    rejects: list[RejectedSource] | None = None,
) -> list[CorpusPassage]:
    """Normalize ``sources`` into a list of `CorpusPassage` records for ``pack_id``.

    Each source is gated against the license whitelist BEFORE any of its passages are
    admitted: a non-whitelisted license rejects the whole source (all its passages) with a
    logged reason, and appends a `RejectedSource` to ``rejects`` if one was provided. A
    passage that fails record validation (missing field, bad license) is skipped and logged
    individually. Returns only the admitted records. Produces NO index.
    """
    out: list[CorpusPassage] = []
    for src in sources:
        provenance = (src.get("source") or "").strip()
        lic = (src.get("license") or "").strip()
        attribution = (src.get("attribution") or "").strip()
        src_tags = list(src.get("tags") or [])

        reason = license_reason(lic)
        if reason:
            log.warning("ingest: rejected source %r — %s", provenance or "<unnamed>", reason)
            if rejects is not None:
                rejects.append(RejectedSource(source=provenance, license=lic, reason=reason))
            continue

        for p in src.get("passages") or []:
            rec: CorpusPassage = {
                "id": (p.get("id") or "").strip(),
                "pack": pack_id,
                "source": provenance,
                "license": lic,
                "attribution": attribution,
                "tags": src_tags + list(p.get("tags") or []),
                "text": (p.get("text") or "").strip(),
            }
            bad = validate_record(rec)
            if bad:
                log.warning("ingest: skipped passage %r — %s", rec.get("id") or "<unnamed>", bad)
                if rejects is not None:
                    rejects.append(
                        RejectedSource(source=provenance, license=lic, reason=f"passage: {bad}")
                    )
                continue
            out.append(rec)
    return out


def write_corpus(records: list[CorpusPassage], path: str) -> None:
    """Write the normalized corpus artifact (the durable asset) as JSON. No index is built."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(records, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
