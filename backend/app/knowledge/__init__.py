# SPDX-License-Identifier: AGPL-3.0-only
"""Domain-reusable knowledge-corpus pipeline (AGPL tool).

A pack-parameterized pipeline that turns openly-licensed sources into a normalized,
license-gated per-pack corpus (`ingest`), builds a lexical index over it (`index`), and
serves it behind the Apache `core.domain.KnowledgeBase` contract (`corpus_kb`). Ingestion
is decoupled from indexing: the corpus is the durable asset; the index is a separate build
that can be swapped (e.g. for a local-embedding vector index) without re-ingesting.

This is a tool, not a domain: it hardcodes no textbook, repository, or domain, and imports
only the Apache contract (`core.domain`) plus stdlib. A pack supplies the sources and loads
the resulting corpus through its own `knowledge()`.
"""

from .ingest import RejectedSource, ingest, write_corpus
from .schema import (
    LICENSE_WHITELIST,
    CorpusPassage,
    is_allowed_license,
    license_reason,
    validate_record,
)

__all__ = [
    "CorpusPassage",
    "LICENSE_WHITELIST",
    "is_allowed_license",
    "license_reason",
    "validate_record",
    "ingest",
    "write_corpus",
    "RejectedSource",
]
