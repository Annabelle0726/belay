# SPDX-License-Identifier: AGPL-3.0-only
"""Corpus-backed KnowledgeBase for the data-science pack (Slice O).

Implements the `core/domain` `KnowledgeBase` protocol over the shipped, license-gated corpus
(`corpus/corpus.json`) via the domain-reusable pipeline (`app/knowledge`): a hermetic,
deterministic lexical BM25 index, no network, no model endpoint, no embeddings, no secrets.

Honesty (the design call, unchanged from Slice F): this is a dumb retriever. It does NOT
screen for leaks. Whether a retrieved passage may enter tutor context is decided by core
governance (`agent/governance.screen_passages`, reusing `pack.leak_evidence`) — the single
gate, the same one the draft path uses. The KB just returns the best lexical matches, each
carrying its attribution + license in the `Passage.citation` field.

The corpus is the durable asset; the BM25 index is a separate build over it. A future
local-embedding vector index could replace the index behind this same contract without
re-ingesting or touching the corpus.
"""

from __future__ import annotations

import json
import os

from ....knowledge import CorpusKB
from ....knowledge.schema import CorpusPassage

_CORPUS_DIR = os.path.join(os.path.dirname(__file__), "corpus")
_CORPUS_PATH = os.path.join(_CORPUS_DIR, "corpus.json")


def load_corpus(path: str = _CORPUS_PATH) -> list[CorpusPassage]:
    """Load a normalized corpus artifact (list of passage records)."""
    with open(path, encoding="utf-8") as fh:
        data: list[CorpusPassage] = json.load(fh)
        return data


class DataScienceKB(CorpusKB):
    """The data-science pack's corpus-backed BM25 KnowledgeBase.

    With no argument it loads the shipped corpus; passing ``corpus`` explicitly (a list of
    passage records) is how tests exercise the gate with a solution-bearing fixture without
    shipping one in the production corpus.
    """

    def __init__(self, corpus: list[CorpusPassage] | None = None) -> None:
        super().__init__(corpus if corpus is not None else load_corpus())
