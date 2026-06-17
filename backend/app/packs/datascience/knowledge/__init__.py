# SPDX-License-Identifier: AGPL-3.0-only
"""Data-science KnowledgeBase: a hermetic lexical retriever over a curated corpus."""

from .kb import DataScienceKB, load_corpus

__all__ = ["DataScienceKB", "load_corpus"]
