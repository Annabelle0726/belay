# CC-B4 — Replace the runner's sandbox: two real boundaries where there are none

*Claude Code prompt. Authored in Cowork, 2026-08-08, from an isolation/sandbox
scan (full scan: `outfitter-waypoint-landscape-2026-08-08.md`, Cowork project;
recorded as a spec at `~/dev/outfitter/specs/08-isolation-tiers.md`).

**This is the highest-value security change available anywhere in the platform,
and this repo's own docs already say so** — `VALIDATION.md` and
`GRADING_SPEC.md` both name "the containerized runner" as the roadmap convergence
point, and `ROADMAP.md` carries it under Deferred edges. This prompt closes it.

The current runner (`backend/app/core/runner/__init__.py`, `_child.py`) executes
student Python in a child process with `setrlimit` resource caps and network
blocking by socket patching. **That is not a boundary.** Any of `ctypes`,
`os.fork`, `subprocess`, or a raw `socket()` through `ctypes` bypasses it in one
line, and `setrlimit`'s `RLIMIT_NPROC` is per-uid and racy against fork bombs.
Student code and the grading harness also share a process today, which means
`inspect.getsource`, `__file__`, `sys.modules`, and tracebacks can all reach the
reference solution — the same defect nbgrader has carried since its issue #483
opened in 2016.

**Scope discipline:** this prompt replaces the execution boundary. It does not
change the `DomainPack` contract, the grading semantics, the governance/leak gate,
or what a `RunnerResult` means to its callers. If you find yourself editing
`core/domain/`, stop — the Apache-2.0 contract package must not move for this.*

---

## 1. Read first

- `backend/app/core/runner/__init__.py` (`run_python`, `RunnerResult`) and
  `_child.py` (`_set_limits`, `_block_network`) — the thing being replaced
- `backend/app/packs/datascience/grader.py` and `specs/GRADING_SPEC.md` — the
  caller, and the "containerized runner is the roadmap convergence point" note
- `~/dev/outfitter/specs/08-isolation-tiers.md` — the platform-level spec this
  implements. Sections 3 (defense in depth), 4 (the autograding-specific hard
  problems), and 7 (where Belay stands) are the normative parts for this task
- `~/dev/cairn/internal/grading/container_runner.go` — **read this before
  designing anything.** Cairn already solved the sibling problem well:
  `--cap-drop ALL`, `--security-opt no-new-privileges`, `--read-only`,
  `--pids-limit`, `--memory` with `--memory-swap` equal (no swap escape),
  `--cpus`, and a fail-safe to `--network none`. Match that flag set rather than
  deriving a different one — two modules diverging on sandbox hardening would be
  a real maintenance hazard, and Cairn's is the reviewed version

## 2. The target: T3 + T4, with T2 available but not required here

Per `specs/08` §3. Concretely, in priority order:

**T3 (container).** Run student code in a container with Cairn's flag set above,
plus a read-only rootfs, a size-capped tmpfs `/tmp`, and an **empty network
namespace** (not a socket monkeypatch — a netns with loopback only cannot be
misconfigured away, which is the entire point).

**T4 (in-sandbox).** A per-submission unprivileged uid, per-run filesystem reset,
and **both CPU-time and wall-clock limits** — a `sleep()` or a blocked read evades
a CPU limit entirely, so both are required, not either.

**T2 (kernel boundary, gVisor).** Support it, do not mandate it. Add a
configuration knob for the OCI runtime (`--runtime=runsc`) that is off by default
and documented, so a deployment with gVisor available gets the stronger boundary
and a dev laptop without it still works. Mandating gVisor here would make the test
suite undevelopable on machines that don't have it, which is the wrong trade for
this repo.

**Consider adopting Piston** (MIT, `isolate`-in-Docker, network off by default,
3s CPU+wall defaults) as the component rather than building the multi-language
path by hand — but only if it fits without contorting `RunnerResult`; Belay
currently needs Python only, so a focused container runner may well be simpler.
State your reasoning either way rather than defaulting silently.

## 3. The harness must move outside the sandbox

This is the part that is easy to skip and is the actual security property.

Per `specs/08` §4: **if student code and test code share a process, the student
wins.** Restructure so the grading harness runs *outside* the sandbox and
communicates with it over a single fd; only student files and public fixtures are
bind-mounted read-only; **hidden tests and the reference solution never enter the
sandbox filesystem at all**; and results cross the boundary as a schema-validated
structured blob with a size cap, never an echoed stdout stream.

If this turns out to require changing `DomainPack.run`'s signature, **stop and
report rather than changing the Apache-2.0 contract** — that is a decision for a
separate, deliberate change with its own licensing review.

## 4. Config and the off-switch

Follow this repo's established pattern for anything that changes runtime posture
(`agent/distress.py`'s `DISTRESS_ROUTING_ENABLED` is the reference): an explicit
setting, a documented default, and a startup warning when the deployment is in the
weaker configuration. Specifically: the existing unsafe in-process runner should
remain reachable **only** behind an explicit opt-in flag named to make its status
obvious (Cairn's precedent: "host-exec runner remains as an explicit unsafe/local
option"), and `PRIVACY.md` / `VALIDATION.md` should record which runner a
deployment is using as an operator-visible fact.

## 5. Tests

- The bypasses that work today must fail: a `ctypes`-based raw socket, a
  `subprocess` spawn, a fork bomb (assert `pids.max` holds), a `sleep()` that
  outlasts the wall clock, and an attempt to read the reference solution path.
  **Write these as tests that FAIL against the current runner first** — that
  failing state is the evidence this task was real. Report the before/after.
- Existing runner tests stay green (the contract to callers is unchanged).
- CI must not require gVisor; the T2 knob is tested for correct flag construction,
  not by running under `runsc`.
- Net-additive count stated, per `VALIDATION.md`'s slice convention.

## 6. Report

- Which of Piston / a focused container runner you chose, and why.
- Whether the harness could move outside the sandbox without touching
  `core/domain/` — and if not, stop there and say so.
- The before/after on §5's bypass tests, explicitly.
- `uv run ruff check .` (or this repo's `cd backend && python -m pytest -q`
  convention) green, with the net-additive test count.
