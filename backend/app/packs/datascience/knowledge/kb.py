# SPDX-License-Identifier: AGPL-3.0-only
"""
Lexical KnowledgeBase for the data-science pack (Slice F).

Implements the `core/domain` `KnowledgeBase` protocol over the shipped corpus
(`corpus/corpus.json`). Retrieval is **hermetic and deterministic**: a pure-Python
TF-IDF cosine ranker, no network, no model endpoint, no embeddings, no secrets.

Honesty (the design call): this is a dumb retriever. It does NOT screen for leaks.
Whether a retrieved passage may enter tutor context is decided by core governance
(`agent/governance.screen_passages`, reusing `pack.leak_evidence`) — the single gate,
the same one the draft path uses. The KB just returns the best lexical matches.

Ranking: TF-IDF (log IDF, raw TF) cosine similarity; ties broken by ascending passage
id so results are stable. Index is built once at construction from the corpus.
"""

from __future__ import annotations

import json
import math
import os
import re

from ....core.domain import Passage

_CORPUS_PATH = os.path.join(os.path.dirname(__file__), "corpus", "corpus.json")
_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


def load_corpus(path: str = _CORPUS_PATH) -> list[dict]:
    """Load the shipped corpus (list of passage dicts)."""
    with open(path, encoding="utf-8") as fh:
        data: list[dict] = json.load(fh)
        return data


class DataScienceKB:
    """In-process lexical KnowledgeBase over a corpus of conceptual passages.

    ``corpus`` is a list of dicts each carrying id/module/concept/title/text/source.
    When omitted, the shipped corpus is loaded. Passing a corpus explicitly is how
    tests exercise the gate with a solution-bearing fixture passage without shipping
    one.
    """

    def __init__(self, corpus: list[dict] | None = None) -> None:
        self._docs: list[dict] = list(corpus if corpus is not None else load_corpus())
        # Index over title + text (concept/module are metadata, not ranked text).
        self._tokens: list[list[str]] = [
            _tokenize(d.get("title", "") + " " + d.get("text", "")) for d in self._docs
        ]
        n = len(self._docs)
        # Document frequency -> smoothed log IDF.
        df: dict[str, int] = {}
        for toks in self._tokens:
            for t in set(toks):
                df[t] = df.get(t, 0) + 1
        self._idf: dict[str, float] = {t: math.log((1 + n) / (1 + d)) + 1.0 for t, d in df.items()}
        # Precompute each doc's TF-IDF vector + norm for cosine.
        self._vecs: list[dict[str, float]] = []
        self._norms: list[float] = []
        for toks in self._tokens:
            vec = self._tfidf(toks)
            self._vecs.append(vec)
            self._norms.append(math.sqrt(sum(w * w for w in vec.values())))

    def _tfidf(self, toks: list[str]) -> dict[str, float]:
        tf: dict[str, int] = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        return {t: c * self._idf.get(t, 0.0) for t, c in tf.items()}

    def _passage(self, d: dict) -> Passage:
        return Passage(
            id=d["id"],
            text=d.get("text", ""),
            citation=d.get("source", ""),
            locator=f"{d.get('module', '')}/{d.get('concept', '')}",
        )

    def search(self, query: str, k: int) -> list[Passage]:
        """Return up to ``k`` passages ranked by TF-IDF cosine similarity to
        ``query`` (descending), ties broken by ascending passage id. Deterministic.
        Passages with zero similarity are not returned."""
        q_vec = self._tfidf(_tokenize(query))
        q_norm = math.sqrt(sum(w * w for w in q_vec.values()))
        scored = []
        for i, d in enumerate(self._docs):
            if q_norm == 0.0 or self._norms[i] == 0.0:
                continue
            dot = sum(w * self._vecs[i].get(t, 0.0) for t, w in q_vec.items())
            if dot <= 0.0:
                continue
            sim = dot / (q_norm * self._norms[i])
            scored.append((sim, d["id"], d))
        # Deterministic order: similarity desc, then id asc (stable tie-break).
        scored.sort(key=lambda s: (-s[0], s[1]))
        return [self._passage(d) for _sim, _id, d in scored[: max(0, k)]]
