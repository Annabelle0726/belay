# datascience knowledge base (corpus + retriever)

The data-science pack's `knowledge()` returns a small, in-process, lexical
KnowledgeBase over the curated corpus in `corpus/corpus.json`. It is the first real
implementation of the `core/domain` `KnowledgeBase` protocol (Slice F).

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
- **Hermetic.** Retrieval is lexical (TF-IDF cosine, pure Python, deterministic, stable
  tie-break by passage id). No network, no model endpoint, no embeddings, no secrets.

## Each passage carries

`id`, `module`, `concept`, `title`, `text`, `source`.

## Content license

The corpus prose in `corpus/corpus.json` is original course concept notes authored for
this framework and is released under **Creative Commons Attribution 4.0 (CC-BY 4.0)**.
Attribute as: *"peer-tutor-framework course concept notes (CC-BY 4.0)."* See also
`docs/PROVENANCE.md`.
