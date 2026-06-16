# Roadmap

What is deliberately not built yet, so a reader knows the edges. These are honest
sketches, not designs; nothing here is implemented, and the framework should not be
read as if it were.

## The cohort layer

The current tutor is single-learner. A cohort layer would add progress sync across a
class, a peer-teaching matcher that connects students into study groups by
complementary strengths, a facilitator stance for a human in the loop, and an
escalation ladder for moving a stuck or distressed student toward a person. None of
this exists; the privacy posture (pseudonymous ids, no rankings, no instructor
surveillance) would constrain how any of it is built.

## The facilitator benchmark family

The behavioral benchmark already has a pluggable family registry
(`@family(name, category)` over the categories `gate_verdict`, `framework_routing`,
`judge_signal`). A facilitator benchmark family would slot into that registry to
exercise the facilitator stance above. It is named as the obvious extension point and
is not yet written.

## Additional domain packs

Data science is the only real pack today (`packs/datascience`); `packs/_skeleton` is a
template echo pack. The pack seam exists precisely so other domains can be added
without touching core, but no second real pack has been built, so the seam's
generality is demonstrated by the skeleton and the reference pack, not yet by a diverse
set.

## The strong-judge benchmark run (pending validation)

The benchmark's deterministic axes are credible now: `never_leak` and `no_solution` are
gate verdicts computed by running `pack.leak_evidence` on the emitted text, not LLM
rubrics, so they do not depend on a judge. The qualitative axes (`grounded`,
`concrete`, `question`) await a strong, distinct judge run at higher repeat counts
(the credible deliverable uses repeats of at least five with a judge that is not a
tutor model under test). That run has not been executed at scale; until it is, the
qualitative signals are reported with their judge model recorded and are not claimed as
validated.

## Distress response

Whether and how the tutor responds to a distress-signaling goal or reflection is a
product and IRB decision, recorded with safe defaults but not built (`docs/PRIVACY.md`
and `docs/EXTRACTION_PLAN.md` section (g)). It is on this list to keep it visible as a
decision someone must make, not a feature that quietly shipped.

## The containerized runner

The execution sandbox (`core/runner`) is honestly a resource, network, and isolation
boundary, not adversarial containment. The closing step is a containerized runner that
adds an OS-level network namespace plus filesystem and PID isolation, converging with
Quad's ephemeral sandboxed graders. Until then, CPU and wall limits are the hard stops.

## Name and publish

The repository name `peer-tutor-framework` is a placeholder and the final name is
pending a domain, org, and package availability check (`docs/PROVENANCE.md`). The
publish step also includes adding the `LICENSE` file: the core and the Quad integration
are written to be Apache-2.0-compatible and the sidecar advertises Apache-2.0, but no
license file is in the tree yet.

## The equity question

Self-hostability is a privacy strength, but operator-hosting alone leaves an equity
question open: requiring an institution to stand up its own compute can itself be a
filter that excludes the institutions with the least capacity. A lower-friction hosted
or consortium path may be needed so that self-hostability is an option, not a
prerequisite. This is an open question, not a planned feature.
