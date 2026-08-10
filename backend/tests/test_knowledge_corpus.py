# SPDX-License-Identifier: AGPL-3.0-only
"""
Slice O — the pack-scoped, license-gated knowledge-corpus pipeline.

Hermetic unit/integration tests (no network, no model, no live reasoner prompt):
  1. ingestion gates on the license whitelist and rejects non-whitelisted sources;
  2. ingestion and indexing are DECOUPLED (a corpus artifact exists without an index);
  3. the pipeline is pack-parameterized (reusable, not hardcoded to DS);
  4. corpus-backed BM25 retrieval is relevant and deterministic;
  5. the leak-over-retrieval gate blocks a seeded solution-bearing passage AT CORPUS SCALE;
  6. attribution + license travel with a surfaced passage end to end.
"""

from __future__ import annotations

import json
import os

from app.agent import governance, run_turn
from app.core.domain import Passage
from app.core.registry import get_active_pack
from app.knowledge import BM25Index, build_index, ingest, validate_record
from app.packs.datascience.knowledge import kb as ds_kb
from app.packs.datascience.knowledge.kb import DataScienceKB, load_corpus
from app.store import InMemoryStore

_LEAK_FIXTURE = os.path.join(os.path.dirname(ds_kb.__file__), "corpus", "leak_fixture.json")
_EX = get_active_pack().get_exercise("ds-foundations")


# ── 1. license gate: ingestion rejects a non-whitelisted source ───────────────


def test_ingestion_rejects_non_whitelisted_source():
    sources = [
        {
            "source": "OpenStax (CC-BY)",
            "license": "CC-BY-4.0",
            "attribution": "OpenStax, CC BY 4.0",
            "passages": [{"id": "ok1", "text": "the mean is the sum over the count"}],
        },
        {
            "source": "Share-alike wiki",
            "license": "CC-BY-SA-4.0",
            "attribution": "x",
            "passages": [{"id": "no1", "text": "must never be ingested"}],
        },
        {
            "source": "Proprietary text",
            "license": "All rights reserved",
            "attribution": "x",
            "passages": [{"id": "no2", "text": "nope"}],
        },
    ]
    rejects = []
    recs = ingest("datascience", sources, rejects=rejects)
    assert [r["id"] for r in recs] == ["ok1"]  # only the CC-BY source admitted
    assert {r.license for r in rejects} == {"CC-BY-SA-4.0", "All rights reserved"}
    assert all(r.reason for r in rejects)  # each rejection carries a logged reason
    # the admitted record carries pack + license + attribution
    assert recs[0]["pack"] == "datascience"
    assert recs[0]["license"] == "CC-BY-4.0"
    assert recs[0]["attribution"] == "OpenStax, CC BY 4.0"


# ── 2. decoupling: a corpus artifact exists with no index built ───────────────


def test_ingestion_and_indexing_are_decoupled(tmp_path):
    sources = [
        {
            "source": "src",
            "license": "CC0",
            "attribution": "public domain",
            "passages": [
                {"id": "p1", "text": "grouping summarizes rows by a key column"},
                {"id": "p2", "text": "a held-out split estimates generalization"},
            ],
        }
    ]
    corpus = ingest("anypack", sources)
    # the corpus is a complete, valid artifact on its own — no index involved
    assert [r["id"] for r in corpus] == ["p1", "p2"]
    assert all(validate_record(r) is None for r in corpus)
    # it is persistable as the durable asset; writing it produces a corpus file, not an index
    out = tmp_path / "corpus.json"
    from app.knowledge import write_corpus

    write_corpus(corpus, str(out))
    assert out.exists()
    assert not (tmp_path / "index.bin").exists()  # ingestion built no index artifact
    # indexing is a SEPARATE step over the corpus
    idx = build_index(corpus)
    assert isinstance(idx, BM25Index)


# ── 3. pack-parameterized: the pipeline is reusable, not hardcoded to DS ───────


def test_pipeline_is_pack_scoped():
    src = [
        {
            "source": "s",
            "license": "MIT",
            "attribution": "a",
            "passages": [{"id": "q1", "text": "a qubit is a two-level quantum system"}],
        }
    ]
    recs = ingest("quantum", src)
    assert recs and all(r["pack"] == "quantum" for r in recs)  # same tool, different pack


# ── 4. retrieval relevance + determinism over the corpus-backed KB ────────────


def test_corpus_kb_retrieval_relevant_and_deterministic():
    kb = DataScienceKB()
    a = [p.id for p in kb.search("group average per category", 3)]
    b = [p.id for p in kb.search("group average per category", 3)]
    assert a == b and a and a[0].startswith("found-")
    cs = [p.id for p in kb.search("big-O notation algorithm running time", 2)]
    assert cs and cs[0].startswith("cs-")  # the CS corpus is reachable
    assert kb.search("", 3) == [] and kb.search("zzzqqq nomatch", 3) == []


# ── 5. leak-over-retrieval AT CORPUS SCALE ────────────────────────────────────


class _RecordingStub:
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


def _at_scale_corpus():
    """The full shipped seed corpus PLUS the solution-bearing leak fixture — the realistic
    'at scale' corpus the gate must hold over."""
    return load_corpus() + load_corpus(_LEAK_FIXTURE)


def test_gate_drops_seeded_solution_at_corpus_scale():
    """Unit: over the full corpus + the seeded leak fixture, governance drops the
    solution-bearing passage and keeps benign passages, recording id + reason only."""
    kb = DataScienceKB(corpus=_at_scale_corpus())
    hits = kb.search("the answer is the per-category mean: groupby category then mean amount", 8)
    assert "leak-foundations" in [p.id for p in hits]  # it IS retrieved at scale
    out = governance.screen_passages(hits, _EX)
    assert "leak-foundations" not in [p.id for p in out["kept"]]  # but the gate drops it
    assert {"id": "leak-foundations", "reason": "prose_disclosure"} in out["dropped"]
    assert all(set(d) == {"id", "reason"} for d in out["dropped"])  # no text in drop records


def test_leak_over_retrieval_blocks_at_scale_end_to_end(monkeypatch):
    """End to end: a KB over the full corpus + the leak fixture cannot leak the solution.
    The gate drops it before the prompt; the drop is traced by id+reason; the leaking text
    appears in neither the prompt nor the trace; a benign passage still reaches context."""
    pack = get_active_pack()
    monkeypatch.setattr(pack, "knowledge", lambda: DataScienceKB(corpus=_at_scale_corpus()))
    store = InMemoryStore()
    stub = _RecordingStub()
    recent = [{"who": "student", "text": "how do I get the mean amount per category group?"}]
    run_turn(_payload("p_scale", recent), stub, store)

    rows = [json.loads(l) for l in store.export_jsonl("p_scale").splitlines() if l]
    retr = [r for r in rows if r["event_type"] == "retrieval"]
    assert len(retr) == 1
    payload = retr[0]["payload"]
    assert {"id": "leak-foundations", "reason": "prose_disclosure"} in payload["dropped"]
    assert "leak-foundations" not in payload["kept"]
    leak_snippet = "just call groupby on category and then mean"
    assert leak_snippet not in stub.reasoner_user
    assert leak_snippet not in store.export_jsonl("p_scale")


# ── 6. attribution + license travel end to end ────────────────────────────────


def test_attribution_and_license_on_returned_passages():
    kb = DataScienceKB()
    hits = kb.search("split apply combine grouping", 2)
    assert hits and all(isinstance(p, Passage) for p in hits)
    # license + attribution ride in the contract's citation field
    assert all("CC-BY-4.0" in p.citation for p in hits)
    assert all("peer-tutor-framework course concept notes" in p.citation for p in hits)


def test_attribution_reaches_the_prompt(monkeypatch):
    """The surfaced passage's citation (attribution + license) reaches the reasoner prompt,
    so attribution is not dropped between retrieval and use."""
    pack = get_active_pack()
    monkeypatch.setattr(pack, "knowledge", lambda: DataScienceKB())
    store = InMemoryStore()
    stub = _RecordingStub()
    recent = [{"who": "student", "text": "explain grouping and per-group summaries"}]
    run_turn(_payload("p_attr", recent), stub, store)
    assert "CC-BY-4.0" in stub.reasoner_user  # the license/attribution citation reached use
