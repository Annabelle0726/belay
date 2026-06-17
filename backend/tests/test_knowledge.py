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

from app.core.domain import Passage
from app.core.registry import get_active_pack
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

    mlp = [
        p.id for p in kb.search("train a small neural net with a hidden layer to reduce loss", 3)
    ]
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
    assert p.id and p.text and p.citation and p.locator  # full Passage shape


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
    kb = get_active_pack().knowledge()  # active pack is datascience
    assert isinstance(kb, DataScienceKB)
    assert len(kb.search("regression", 1)) == 1


def test_skeleton_knowledge_is_none():
    from app.packs._skeleton import SkeletonPack

    assert SkeletonPack().knowledge() is None


# ── the leak-over-retrieval gate (the safety core of Slice F) ─────────────────

import json

from app.agent import governance, run_turn
from app.store import InMemoryStore

# A reference passage that DISCLOSES the ds-foundations solution in prose (imperative
# + the essential operation tokens). No code fence, so it trips prose_disclosure
# without running the grader. This is the retrieval-side analogue of the worst-case
# leaking reasoner in test_student_rule_cannot_leak.
_POISON = {
    "id": "poison-foundations",
    "module": "wrangling-eda",
    "concept": "group-by and aggregation",
    "title": "leak",
    "source": "fixture",
    "text": (
        "For this exercise the answer is the per-category mean: just call groupby "
        "on category and then mean on amount, and you are done."
    ),
}
_BENIGN = {
    "id": "benign-foundations",
    "module": "wrangling-eda",
    "concept": "group-by and aggregation",
    "title": "Split-apply-combine",
    "source": "peer-tutor-framework course concept notes (CC-BY 4.0)",
    "text": (
        "Split the rows into groups defined by a key column, summarize each group, "
        "and combine the summaries back into one table. Thinking in this shape "
        "keeps the intent clear and the code vectorized."
    ),
}
_EX = get_active_pack().get_exercise("ds-foundations")


def _payload(pid, recent):
    return {
        "participant_id": pid,
        "exercise": _EX,
        "event": "chat",
        "mode": "study",
        "stance": "peer",
        "source": "import pandas as pd",
        "result": {
            "ok": True,
            "goalMet": False,
            "metric": None,
            "pack": {"id": "datascience", "summary": "0/1 checks passed"},
        },
        "recent": recent,
        "signals": None,
    }


class _RecordingStub:
    """Benign tutor; captures the reasoner's serialized context (the user prompt)."""

    def __init__(self):
        self.reasoner_user = ""

    def json(self, *, role, tier, system, user, max_tokens=800, reasoning_effort=None):
        if role == "reasoner":
            self.reasoner_user = user
            return {
                "message": "What single number should each category collapse to?",
                "check_question": None,
                "confidence": 0.8,
                "grasped": [],
                "shaky": [],
            }
        if role == "planner":
            return {
                "affective_state": "curious",
                "affect_reasoning": "x",
                "intervention": "co_reason",
                "target_concept": "g",
                "planner_note": "n",
                "confidence": 0.8,
            }
        return {
            "needs_revision": False,
            "confidence": 0.8,
            "leak_risk": "none",
            "self_critique": "ok",
            "reasons": [],
        }


def test_screen_drops_solution_bearing_passage_keeps_benign():
    """Unit: core governance drops a solution-bearing passage and keeps a benign one,
    recording the drop by id + reason only (no text)."""
    from app.core.domain import Passage

    poison = Passage(id=_POISON["id"], text=_POISON["text"], citation="fixture", locator="x")
    benign = Passage(id=_BENIGN["id"], text=_BENIGN["text"], citation="notes", locator="y")
    out = governance.screen_passages([poison, benign], _EX)
    assert [p.id for p in out["kept"]] == [_BENIGN["id"]]
    assert out["dropped"] == [{"id": _POISON["id"], "reason": "prose_disclosure"}]
    assert out["retrieved"] == 2
    # the drop record carries NO passage text
    assert all(set(d) == {"id", "reason"} for d in out["dropped"])


def test_leak_over_retrieval_blocks_end_to_end(monkeypatch):
    """The retrieval analogue of test_student_rule_cannot_leak: a KB that surfaces a
    solution-bearing passage cannot leak it into context. The gate drops it before the
    prompt, the drop is traced by id+reason, and the leaking text appears nowhere in
    the trace or the prompt."""
    pack = get_active_pack()
    monkeypatch.setattr(pack, "knowledge", lambda: DataScienceKB(corpus=[_BENIGN, _POISON]))
    store = InMemoryStore()
    stub = _RecordingStub()
    recent = [{"who": "student", "text": "how do I get the mean amount per category group?"}]
    run_turn(_payload("p_leak_ret", recent), stub, store)

    rows = [json.loads(l) for l in store.export_jsonl("p_leak_ret").splitlines() if l]
    retr = [r for r in rows if r["event_type"] == "retrieval"]
    assert len(retr) == 1, [r["event_type"] for r in rows]
    payload = retr[0]["payload"]
    # poison dropped with reason; benign kept; poison never in kept
    assert {"id": "poison-foundations", "reason": "prose_disclosure"} in payload["dropped"]
    assert "benign-foundations" in payload["kept"]
    assert "poison-foundations" not in payload["kept"]
    # the leaking passage text reached NEITHER the prompt NOR the trace
    leak_snippet = "just call groupby on category and then mean"
    assert leak_snippet not in stub.reasoner_user
    assert leak_snippet not in store.export_jsonl("p_leak_ret")
    # the benign passage DID reach the prompt context
    assert (
        "split-apply-combine".replace("-", " ") in stub.reasoner_user.lower()
        or "combine the summaries" in stub.reasoner_user
    )


def test_benign_only_retrieval_emits_event_with_no_drops(monkeypatch):
    """Negative control: with only benign passages, retrieval runs, all survive, and
    the drop list is empty."""
    pack = get_active_pack()
    monkeypatch.setattr(pack, "knowledge", lambda: DataScienceKB(corpus=[_BENIGN]))
    store = InMemoryStore()
    recent = [{"who": "student", "text": "explain grouping and per-group summaries"}]
    run_turn(_payload("p_benign", recent), _RecordingStub(), store)
    rows = [json.loads(l) for l in store.export_jsonl("p_benign").splitlines() if l]
    retr = [r for r in rows if r["event_type"] == "retrieval"][0]
    assert retr["payload"]["dropped"] == [] and "benign-foundations" in retr["payload"]["kept"]


def test_none_path_emits_no_retrieval_event(monkeypatch):
    """None-path no-op: with knowledge() None, no retrieval runs even when the student
    asks something — the trace is exactly the turn event, byte-identical to before."""
    pack = get_active_pack()
    monkeypatch.setattr(pack, "knowledge", lambda: None)
    store = InMemoryStore()
    recent = [{"who": "student", "text": "how do I group and average?"}]
    run_turn(_payload("p_none", recent), _RecordingStub(), store)
    types = [json.loads(l)["event_type"] for l in store.export_jsonl("p_none").splitlines() if l]
    assert types == ["turn"]


def test_no_student_query_means_no_retrieval(monkeypatch):
    """Trigger discipline: a turn with no student message runs no retrieval even though
    the pack has a KB (keeps the 'plain turn = one row' invariant)."""
    pack = get_active_pack()
    monkeypatch.setattr(pack, "knowledge", lambda: DataScienceKB(corpus=[_BENIGN, _POISON]))
    store = InMemoryStore()
    run_turn(_payload("p_noq", recent=[]), _RecordingStub(), store)
    types = [json.loads(l)["event_type"] for l in store.export_jsonl("p_noq").splitlines() if l]
    assert types == ["turn"]
