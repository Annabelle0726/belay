# EduCloud ecosystem — shared conventions

This repo (`belay`) is the AI peer tutor of the EduCloud ecosystem, an
open-source GitHub Classroom replacement. Siblings: `cairn` (classroom/LMS),
`portage` (LLM routing engine), `outfitter` (compute broker), `waypoint`
(hosting/identity), `educloud` (umbrella strategy/decisions/SYSTEM.md).
`portage-local` is a separate personal deployment, currently on hold — not
part of this ecosystem's active work.

## The platform invariant

No component trusts a model's — or a provider's — self-report. A
deterministic check decides success, always. Before citing a vendor's claim
(pricing, precision, model catalog, uptime, API behavior) as fact in a doc
or a decision, verify it against the live API/service, not the marketing
page. This has mattered concretely more than once already (Morph's
precision claims vs. Jetstream2/AI Verde's, over in `portage`).

This repo carries an extra version of the same invariant: Belay's grades
firewall and distress-safety design (`PRIVACY.md`) exist precisely because a
tutor's own output can't be trusted as automatically safe or automatically
non-graded — those properties are enforced structurally, not asserted.

## The CC-* prompt namespace — check before you number

Claude Code prompts across all six repos share one numbering namespace:
`CC-P*` (Portage), `CC-CA*` (Cairn), `CC-B*` (Belay — this repo), `CC-O*`
(Outfitter), `CC-W*` (Waypoint), `CC-HB*`/`CC-C*` (historical, closed
series). **A number means one thing platform-wide — collisions have
happened twice already** (CC-P9/P10 reused by accident, CC-C1 reused by
accident). Before creating a new prompt:

1. Read `../educloud/DOCUMENTATION.md`'s "Prompt-number namespace" section
   for the next free number in your series (find the actual path — it's a
   sibling directory, don't assume the relative path is exactly `../educloud`
   without checking).
2. Also check this repo's own `docs/prompts/` directory directly — the
   registry can drift; the directory listing is ground truth.
3. Use one higher than the max of both, then update the registry.

The `/new-cc-prompt` custom command in this repo does steps 1-3
automatically — prefer it over doing this by hand.

Prompt files live in `docs/prompts/CC-<series><n>-<slug>.md` and follow this
shape: a real title (not a placeholder); an italicized context block
(`*Claude Code prompt. Authored [where/when], from [what triggered this —
a finding, an instruction, a prior prompt's report]`) stating plainly what's
already known/verified and what this prompt needs to resolve; numbered
sections (what to read first, what to do, in dependency order); a closing
numbered **Report** section listing exactly what the executor must report
back — including anything that diverged from the happy path or couldn't be
verified. Never omit the Report section.

## Git conventions

- No `Co-Authored-By: Claude` trailers in this repo's commits. Check actual
  trailers, not prose: `git log -5 --format='%(trailers:key=Co-Authored-By)'`
  should print nothing — a plain `grep -c Co-Authored-By` over the log can
  false-positive on prose describing the convention (caught in Cairn by
  CC-CA5, 2026-08-09).
- Prefer new commits over amends; never force-push without being asked.

## Where things are

- `../educloud/SYSTEM.md` — the eleven shared platform contracts every
  module implements against
- `../educloud/DOCUMENTATION.md` — the full doc index and the CC-* namespace
  tracker
- `ARCHITECTURE.md` — the architecture spec; `INSTRUCTOR_MODE.md` — the
  instructor-mode design (session-ready)
- `VALIDATION.md` — the build/verification record; treat as ground truth
  over any doc that disagrees with it
- `GROUND_TRUTH.md` — read-only audit; don't edit casually
- `PRIVACY.md` — the distress-safety design and the grades firewall; read
  before touching anything that could leak a grade signal into tutoring
  output or vice versa
- `ROADMAP.md` — every item is cited to an in-tree source; keep that
  discipline when adding to it
- `docs/prompts/CC-B1`–`CC-B4` — prompts executed so far
