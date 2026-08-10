# datascience knowledge base (corpus + retriever)

The data-science pack's `knowledge()` returns a small, in-process, lexical KnowledgeBase
over the curated corpus in `corpus/corpus.json`, built through the domain-reusable,
license-gated pipeline in `app/knowledge/` (Slice O; first introduced in Slice F). The
corpus is the durable asset; the lexical (BM25) index is a separate build over it.

## What this is (and is not)

- **Conceptual reference only.** Every passage explains a concept behind one of the
  three exercises (`ds-foundations`, `ds-regression`, `ds-mlp`). **No passage contains an
  exercise solution** — not the reference code, not a literal answer value, and not the
  essential operation tokens that the prose-leak heuristic keys on. A test screens every
  shipped passage through the governance gate against all three exercises and asserts
  none are dropped (`tests/test_knowledge.py`).
- **Not authority over governance.** Retrieved passages are *candidates*. They pass
  through the deterministic core governance leak gate (`governance.screen_passages`,
  reusing `pack.leak_evidence`) before any can enter tutor context. A solution-bearing
  passage is dropped there, exactly as a solution-bearing draft is — see the
  leak-over-retrieval contract at `core/domain/pack.py` (the `KnowledgeBase` docstring).
- **Hermetic.** Retrieval is lexical (BM25, pure Python, deterministic, stable tie-break by
  passage id). No network, no model endpoint, no embeddings, no secrets. A local-embedding
  vector index could replace the lexical index later behind the same `KnowledgeBase`
  contract, with no re-ingest (see `ROADMAP.md`).

## Each passage carries

`id`, `pack`, `source`, `license`, `attribution`, `tags`, `text` (the normalized corpus
schema; see `app/knowledge/schema.py`). When a passage is surfaced, its attribution and
license ride in the contract's `Passage.citation` field.

## Content license

The corpus prose in `corpus/corpus.json` is original course concept notes authored for
this framework and is released under **Creative Commons Attribution 4.0 (CC-BY 4.0)**.
Attribute as: *"peer-tutor-framework course concept notes (CC-BY 4.0)."* Ingestion admits
only whitelisted-license content (public-domain, CC0, CC-BY, MIT, Apache-2.0, BSD) and
records each passage's license and attribution; see `LICENSING.md` (Corpus content).

`corpus/leak_fixture.json` is a TEST-ONLY solution-bearing passage used to prove the
leak-over-retrieval gate at corpus scale. It is not part of the production corpus and is
never loaded by `knowledge()`.
