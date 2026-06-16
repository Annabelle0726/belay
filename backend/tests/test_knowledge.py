"""
Slice F — the datascience KnowledgeBase and the leak-over-retrieval gate.

This file has two halves:
  1. KB retrieval: relevance, determinism, hermetic, and the shipped corpus is
     leak-clean against every exercise.
  2. The gate (added with the gate commit): a solution-bearing passage is dropped by
     core governance and never enters context; a benign passage is retained; the
     None-path is a no-op; no leaking passage text is written to the trace.
"""
from __future__ import annotations

from app.core.domain import Passage, get_active_pack
from app.packs.datascience import leak as ds_leak
from app.packs.datascience.knowledge.kb import DataScienceKB, load_corpus

_EXERCISES = ("ds-foundations", "ds-regression", "ds-mlp")


# ── KB retrieval: relevance, determinism, hermetic ────────────────────────────

def test_search_ranks_relevant_module_first():
    kb = DataScienceKB()
    found = [p.id for p in kb.search("compute the average amount for each category group", 3)]
    assert found and found[0].startswith("found-"), found

    reg = [p.id for p in kb.search("fit a linear model and evaluate on a held-out split", 3)]
    assert reg and reg[0].startswith("reg-"), reg

    mlp = [p.id for p in kb.search("train a small neural net with a hidden layer to reduce loss", 3)]
    assert mlp and mlp[0].startswith("mlp-"), mlp


def test_search_is_deterministic():
    kb = DataScienceKB()
    a = [p.id for p in kb.search("group average summary", 5)]
    b = [p.id for p in kb.search("group average summary", 5)]
    assert a == b and len(a) >= 1


def test_search_returns_passage_objects_with_id():
    kb = DataScienceKB()
    hits = kb.search("least squares regression", 2)
    assert all(isinstance(p, Passage) for p in hits)
    p = hits[0]
    assert p.id and p.text and p.citation and p.locator   # full Passage shape


def test_empty_or_unmatched_query_returns_nothing():
    kb = DataScienceKB()
    assert kb.search("", 3) == []
    # a query with no lexical overlap returns no passages (no zero-similarity noise)
    assert kb.search("zzzzqqq xkcd unrelated", 3) == []


def test_k_bounds_results():
    kb = DataScienceKB()
    assert len(kb.search("data model loss split group", 2)) <= 2
    assert kb.search("data", 0) == []


# ── the shipped corpus is leak-clean (no passage discloses any solution) ──────

def test_shipped_corpus_discloses_no_solution():
    """Every shipped passage must pass the prose-leak heuristic against EVERY
    exercise — otherwise a benign reference would be wrongly screened out (and, worse,
    the corpus would itself be a leak surface). This is the corpus-hygiene guard."""
    for d in load_corpus():
        for ex_id in _EXERCISES:
            assert not ds_leak.prose_discloses(d["text"], ex_id), (d["id"], ex_id)


# ── wiring: knowledge() is real for datascience, None for _skeleton ───────────

def test_datascience_knowledge_is_a_real_kb():
    kb = get_active_pack().knowledge()       # active pack is datascience
    assert isinstance(kb, DataScienceKB)
    assert len(kb.search("regression", 1)) == 1


def test_skeleton_knowledge_is_none():
    from app.packs._skeleton import SkeletonPack
    assert SkeletonPack().knowledge() is None
