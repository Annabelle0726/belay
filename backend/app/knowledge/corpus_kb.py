# SPDX-License-Identifier: AGPL-3.0-only
"""Corpus-backed KnowledgeBase: the BM25 index behind the Apache `KnowledgeBase` contract.

`CorpusKB` implements `core.domain.KnowledgeBase.search(query, k) -> list[Passage]` over a
normalized corpus, ranked by the lexical BM25 index. It is a dumb retriever: it does NOT
screen for leaks. Whether a retrieved passage may enter tutor context is decided by core
governance (`agent.governance.screen_passages`, reusing `pack.leak_evidence`) — the single
gate the draft path uses. CorpusKB just returns the best lexical matches.

Attribution travels with the passage: each returned `Passage` carries the per-passage
attribution and license in its ``citation`` field (the contract field that the context
layer already surfaces to the prompt), and the source/tags in ``locator``. Nothing about
the corpus or this class touches the Apache contract — a local-embedding vector index could
replace the BM25 index later without changing `search`'s signature or the corpus.
"""

from __future__ import annotations

from ..core.domain import Passage
from .index import build_index, tokenize
from .schema import CorpusPassage


def _citation(rec: CorpusPassage) -> str:
    """The credit line surfaced with a passage: attribution and license when present,
    falling back to the source provenance so a citation is never empty for a real passage."""
    attribution = (rec.get("attribution") or "").strip()
    lic = (rec.get("license") or "").strip()
    if attribution and lic:
        return f"{attribution} ({lic})"
    return attribution or lic or (rec.get("source") or "").strip()


def _locator(rec: CorpusPassage) -> str:
    """Where the passage sits: the tags (module / concept / topic), falling back to source."""
    tags = rec.get("tags") or []
    joined = "; ".join(t for t in tags if t)
    return joined or (rec.get("source") or "").strip()


class CorpusKB:
    """In-process BM25 KnowledgeBase over a list of corpus passage records.

    ``records`` is the normalized corpus (each carrying at least id + text; full records
    also carry pack/source/license/attribution/tags). Passing records explicitly is how a
    pack loads its shipped corpus and how tests exercise the gate with a solution-bearing
    fixture without shipping one in the production corpus.
    """

    def __init__(self, records: list[CorpusPassage]) -> None:
        self._records: list[CorpusPassage] = list(records)
        # id -> record; on duplicate ids, the first wins (stable, deterministic).
        self._by_id: dict[str, CorpusPassage] = {}
        for r in self._records:
            rid = r.get("id", "")
            if rid and rid not in self._by_id:
                self._by_id[rid] = r
        self._index = build_index(self._records)

    def _passage(self, rec: CorpusPassage) -> Passage:
        return Passage(
            id=rec.get("id", ""),
            text=rec.get("text", ""),
            citation=_citation(rec),
            locator=_locator(rec),
        )

    def search(self, query: str, k: int) -> list[Passage]:
        """Return up to ``k`` passages ranked by BM25 similarity to ``query`` (descending),
        ties broken by ascending id. Deterministic. Zero-score passages are not returned.
        Each returned `Passage` carries attribution + license in ``citation``."""
        hits = self._index.search(tokenize(query), max(0, k))
        return [
            self._passage(self._by_id[doc_id]) for doc_id, _score in hits if doc_id in self._by_id
        ]
