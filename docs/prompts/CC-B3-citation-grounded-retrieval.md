# CC-B3 — Citation-grounded answers over the existing knowledge base

*Claude Code prompt. Authored in Cowork, 2026-08-08, from a provider-pattern
scan (`morph-full-and-provider-landscape-2026-08-08.md`, Cowork project).
Investigated Perplexity's Sonar API and "Internal Knowledge Search" product
— both hosted-only, both would send document/query content to a third
party, both disqualified for this platform's FERPA/sovereignty posture. But
the pattern underneath them — **retrieve first, generate second, cite every
claim to a specific retrieved passage** — is buildable directly on top of
`packs/datascience/knowledge/kb.py`'s existing hermetic, license-gated,
pure-Python retriever with no vendor dependency at all.

**What exists today** (`ARCHITECTURE.md`'s knowledge-corpus section,
`VALIDATION.md` Slice F): retrieval returns passages, each already carrying
attribution + license via the contract's `Passage.citation` field
(`app/knowledge/corpus_kb.py`), which the context layer already passes to
the prompt. **What's missing:** nothing constrains the tutor's *generated
answer* to actually ground itself in what was retrieved, and nothing
attaches a verifiable per-claim citation back to a specific passage in the
tutor's output. Today a passage can ride along in context without the
tutor's answer being checked against it at all — the citation data exists
upstream and dead-ends before it reaches the student.*

---

## 1. Read first

- `backend/app/core/domain/pack.py` (`Passage`, `KnowledgeBase` protocol,
  `Passage.citation`)
- `backend/app/packs/datascience/knowledge/kb.py`,
  `backend/app/knowledge/corpus_kb.py`
- `backend/app/agent/context.py` — how `ctx["knowledge"]` reaches the
  prompt today
- `backend/app/agent/governance.py` — the leak/leak-over-retrieval gate
  this must not weaken or bypass. **This is the load-bearing constraint of
  this whole prompt:** citation-grounding must run in addition to the
  existing leak gate, never as a substitute for it, and must not create a
  new path for a retrieved passage's content to reach the student
  unscreened. `governance.screen_passages` already runs before any passage
  enters context — this task adds a downstream check on the *generated
  answer*, not a new upstream retrieval path.

## 2. Add a groundedness check

After the Reasoner/Peer-Reasoner writes its response (same site as the
existing Self-Evaluation critique step, per `ARCHITECTURE.md`'s "the agent
loop" section — check whether it belongs there or as a distinct step),
check whether the response's substantive claims are actually traceable to
a passage present in `ctx["knowledge"]` for that turn. This can be as simple
as a deterministic overlap/entailment check against the surviving
(post-leak-gate) passages — keep it in the platform's existing "deterministic
where possible" register rather than reaching for another model call if a
simpler check suffices; state your reasoning if you do add a model-based
check.

## 3. Attach the citation

Where a claim is grounded, attach `Passage.citation` inline or as a trailing
reference — pick whichever fits the existing tutor-response schema in
`schemas.py` least disruptively. Where a claim in the response is *not*
grounded in any retrieved passage, decide (and state your reasoning): flag
it distinctly in the trace, soften the claim, or leave ungrounded content as
today's baseline behavior (no regression) while the trace records the gap.
**Do not silently drop or rewrite ungrounded content as if this were a leak
check** — this is a groundedness signal, a separate concern from leak
prevention, and conflating the two would blur a distinction this platform's
existing governance gate deliberately keeps separate (leak vs. tone vs.
distress are already three distinct layers for exactly this reason).

## 4. Trace event

Additive, following the existing convention (`retrieval` event in Slice F):
record which passages were available, which were cited, and whether any
substantive claim in the response had no supporting passage — content-free
in the sense that it never repeats passage text redundantly beyond the
citation id, matching the platform's existing trace-minimalism discipline.

## 5. Tests

- A grounded-response case: response with a claim traceable to a passage,
  citation correctly attached.
- An ungrounded case: response makes a claim with no supporting passage,
  handled per your §3 decision, not silently.
- Confirm the leak gate still runs and still drops solution-bearing
  passages before they ever reach this new check — i.e., this check only
  ever sees passages that already survived `screen_passages`.
- The None-path (`knowledge()` returns None, e.g. `_skeleton`) stays a
  byte-identical no-op, same as every other retrieval-adjacent feature in
  this codebase.

## 6. Report

- Where in the pipeline the check landed and why.
- How ungrounded claims are handled, and why that choice over the
  alternatives in §3.
- `uv run ruff check .` and the full backend suite, green, net-additive
  count stated.
- Confirm explicitly: no change to what passages can reach context, no
  weakening of the leak gate — this is purely a downstream, additive check.
