# SPDX-License-Identifier: AGPL-3.0-only
"""Lexical (BM25) indexing step over a normalized corpus.

A SEPARATE step from ingestion: it reads the normalized corpus (the durable asset) and
builds an in-memory Okapi BM25 index over each passage's text. Hermetic and deterministic:
pure Python, no network, no model, no embeddings, no secrets.

The index sits behind the `KnowledgeBase` contract (see `corpus_kb`), so a future
local-embedding vector index can replace or supplement BM25 without touching the corpus or
the contract. Ranking is BM25 score descending, ties broken by ascending passage id;
passages with zero score (no shared query term) are not returned.
"""

from __future__ import annotations

import math
import re

from .schema import CorpusPassage

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokenization (the single tokenizer for index and query)."""
    return _TOKEN.findall((text or "").lower())


class BM25Index:
    """In-memory Okapi BM25 index over (id, tokens) documents.

    Parameters ``k1`` and ``b`` are the standard BM25 knobs (term-frequency saturation and
    length normalization). The index is built once and queried many times; it is pure data,
    so it is deterministic and trivially reproducible from the corpus.
    """

    def __init__(
        self,
        ids: list[str],
        tokenized_docs: list[list[str]],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self._ids = list(ids)
        self._k1 = k1
        self._b = b
        self._tf: list[dict[str, int]] = []
        self._len: list[int] = []
        df: dict[str, int] = {}
        for toks in tokenized_docs:
            tf: dict[str, int] = {}
            for t in toks:
                tf[t] = tf.get(t, 0) + 1
            self._tf.append(tf)
            self._len.append(len(toks))
            for t in tf:
                df[t] = df.get(t, 0) + 1
        n = len(tokenized_docs)
        self._avgdl = (sum(self._len) / n) if n else 0.0
        # Okapi BM25 IDF, floored at 0 by the +1 inside the log so a term in every doc
        # contributes a non-negative weight rather than a negative one.
        self._idf: dict[str, float] = {
            t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()
        }

    def search(self, query_tokens: list[str], k: int) -> list[tuple[str, float]]:
        """Return up to ``k`` ``(id, score)`` pairs, BM25 score descending, ties broken by
        ascending id. Documents with zero score are omitted. Deterministic."""
        if k <= 0 or not query_tokens:
            return []
        q = set(query_tokens)
        scored: list[tuple[float, str]] = []
        for i, doc_id in enumerate(self._ids):
            tf = self._tf[i]
            dl = self._len[i]
            denom_norm = self._k1 * (
                1 - self._b + self._b * (dl / self._avgdl if self._avgdl else 0.0)
            )
            score = 0.0
            for t in q:
                f = tf.get(t, 0)
                if not f:
                    continue
                score += self._idf.get(t, 0.0) * (f * (self._k1 + 1)) / (f + denom_norm)
            if score > 0.0:
                scored.append((score, doc_id))
        scored.sort(key=lambda s: (-s[0], s[1]))
        return [(doc_id, score) for score, doc_id in scored[:k]]


def build_index(records: list[CorpusPassage], *, k1: float = 1.5, b: float = 0.75) -> BM25Index:
    """Build a BM25 index over ``records``' text. A separate step from ingestion: the
    corpus must already exist; this only indexes it."""
    ids = [r.get("id", "") for r in records]
    docs = [tokenize(r.get("text", "")) for r in records]
    return BM25Index(ids, docs, k1=k1, b=b)
