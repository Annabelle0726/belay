# peer-tutor-framework

A generalizable, evaluation-first peer-tutor framework. Its defining property: the
tutor cannot leak an exercise solution because a deterministic, executable Governance
gate runs the draft through the active domain's grader and strips any full solution,
rather than merely asking the model not to.

> The repository name `peer-tutor-framework` is a placeholder. The final name is
> pending and will be set in a single atomic commit at the publish step.

## What it is

The tutor runs an evaluation-first loop per turn: a Planner picks one pedagogical
move, a Peer-Reasoner writes the message, a Self-Evaluation critiques it against a
stance rubric, a bounded refine fixes a failing draft, a deterministic Governance gate
runs last, and Memory merges what the student now grasps. The reference domain is
general data science (the "Robin" pack). This framework is original; its first
implementation was built within a quantum tutor, and the domain-agnostic core was
extracted from that codebase. The quantum-specific application stays in its own
repository and is not part of this framework.

Three properties distinguish it:

- Deterministic governance. The no-leak rule is an executable gate, not a prompt
  instruction. Leak-detection has a ground-truth oracle (the pack's grader plus the
  known solution), so the gate decides post-hoc and is supreme over everything,
  including a student goal that demands the answer.
- Privacy by architecture. Identity is a pseudonymous host id only (for example
  `gh:12345`); PII is rejected at the sidecar boundary; there is no write path to
  grades and no rankings. Goals and reflections are pseudonymous and never surfaced to
  an instructor.
- Compute-agnostic, self-hosted first. The default provider is `openai_compatible`
  pointed at a local Ollama or vLLM endpoint, so the tutor can run entirely on
  institutional compute with no external API in the data path.

## Quickstart

The fastest path is the container, which is SQLite-default and points at a local
OpenAI-compatible model endpoint with no external API.

```bash
docker compose up --build                    # SQLite + openai_compatible
docker compose --profile postgres up --build # Postgres opt-in (scale)
```

The container CMD runs the preflight doctor informationally and then serves on port
8000. To run the doctor directly:

```bash
cd backend && python -m app.preflight                 # checks config, store, provider
cd backend && python -m app.preflight --skip-provider # skip the endpoint probe
```

Preflight prints `[PASS] <check>` / `[FAIL] <check>` for `config`, `store`, and
(unless skipped) `provider`, then `preflight: OK` or `preflight: FAILED` with a
non-zero exit on failure.

To run the suite and the local server from source, see `VALIDATION.md` (the canonical
runbook); env knobs are defined in `backend/app/config.py`. The operationally relevant
ones:

| Env var | Default | Purpose |
|---|---|---|
| `PROVIDER` | `openai_compatible` | Inference provider; also recorded in the trace |
| `OPENAI_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible endpoint (Ollama/vLLM) |
| `OPENAI_API_KEY` | `EMPTY` | Key for the endpoint (local endpoints ignore it) |
| `MODEL_FAST` | `llama3.2` | Concrete model for the fast tier |
| `MODEL_STRONG` | `llama3.2` | Concrete model for the strong tier |
| `OPENAI_REASONING` | `0` | Send `reasoning_effort` (strong tier) only if on |
| `TUTOR_PACK` | `datascience` | Active domain pack |
| `STORE_BACKEND` | `sql` | `sql` (durable) or `memory` (ephemeral) |
| `DATABASE_URL` | `sqlite:///./qimvp.db` | Store DSN; a Postgres DSN opts into Postgres |
| `MAX_REFINE` | `1` | Reasoner revisions after a failing self-eval |
| `TAU_ESCALATE` / `MAX_ESCALATE` | `0.55` / `1` | Re-run at higher effort when under-confident |
| `TAU_ABSTAIN` | `0.35` | Peer-only honest abstention floor |

## Adding a domain pack

A pack implements the `DomainPack` protocol (`backend/app/core/domain/pack.py`):
`curriculum`, `get_exercise`, `run`, `program_signature`, `verify_worked_example`,
`misconceptions`, `leak_evidence`, and optional `knowledge`. Start from
`backend/app/packs/_skeleton/` (a dependency-free echo pack used for core-only tests)
and model a real one on `backend/app/packs/datascience/` (the reference pack: a
taxonomy, a curriculum, declarative grading specs, a misconception library, and
combined leak evidence). Register the pack's factory in
`backend/app/core/domain/registry.py` and select it with `TUTOR_PACK`. Core never
imports a pack at module load; the dependency arrow points from packs to core.

A pack's optional `knowledge()` is backed by the domain-reusable corpus pipeline
(`backend/app/knowledge/`): a license-gated ingestion step produces a normalized,
pack-scoped corpus (only public-domain / CC0 / CC-BY / MIT / Apache-2.0 / BSD content is
admitted, with per-passage license and attribution recorded), and a separate lexical (BM25)
indexing step serves it behind the unchanged `KnowledgeBase` contract. Retrieval is lexical
now; a local-embedding vector index can be added later behind the same contract with no
re-ingest. Only a tiny seed corpus ships in-tree; ingesting real sources is a later operator
step. Retrieved passages pass through the same deterministic leak gate as a generated draft,
so retrieving an answer is not a loophole. See `ARCHITECTURE.md` and `ROADMAP.md`.

## Pointing at a provider

`PROVIDER` selects the provider; the fast/strong tier policy (Planner fast, Reasoner
strong, Self-Evaluator fast) lives in core and is provider-agnostic. Only the
tier-to-model mapping is per-provider config.

- `openai_compatible` (default, self-hosted first): set `OPENAI_BASE_URL`,
  `MODEL_FAST`, `MODEL_STRONG`, and `OPENAI_API_KEY`. Sends no reasoning parameter
  unless `OPENAI_REASONING=1`, so it works with ordinary local models.
- `anthropic` (hosted convenience): set `ANTHROPIC_API_KEY`; tiers default to
  `claude-haiku-4-5-20251001` (fast) and `claude-sonnet-4-6` (strong); extended
  thinking is on by default.
- `bedrock`: a documented stub, not live. Its Amazon Nova tier mapping is testable but
  a call raises.

## Quad sidecar

A versioned HTTP/JSON sidecar exposes the existing tutor loop to the EduCloud Quad
control plane at base path `/quad/v1` (`backend/app/integrations/quad/`, mounted on the
main app). It imports core only, advertises its posture at `/quad/v1/capabilities`
(pseudonymous identity, grades read-only with no write path, Apache-2.0), runs one
tutor turn at `/quad/v1/turn`, and rejects PII at the boundary with a 422.

## Behavioral benchmark

A portable, pack- and provider-parameterized benchmark lives in
`backend/evals/behavioral/`. Run it from `backend/`:

```bash
python -m evals.behavioral --pack datascience [--provider P] [--repeats N] \
    [--judge-provider P] [--temperature 0] [--families a,b,c] [--no-judge] [--out report.json]
```

`no_solution` and `never_leak` are deterministic gate verdicts (the harness runs
`pack.leak_evidence` on the emitted text), not LLM rubrics. Qualitative families use a
separate strong judge configured via `JUDGE_PROVIDER` / `JUDGE_MODEL`; if the judge
model equals a tutor model under test the report marks those families
`credible: false` / `self_judged: true`. The deterministic axes are credible today;
the strong-judge run at higher repeats is pending.

## License

The framework core and the Quad integration are intended for open-source release and
are written to be Apache-2.0-compatible, importing only from the framework core. The
`/quad/v1/capabilities` document advertises `"license": "Apache-2.0"`. Note honestly:
there is no `LICENSE` file in the repository yet. Adding it is part of the
name-and-publish step; until then the license is stated intent, not a file in the tree.
