#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""
Belay's implementation of the `leak` profile of the verifier contract.

The contract lives in the sibling `verifier-contract` repository (`SPEC.md`,
`schema/request.schema.json`, `schema/verdict.schema.json`). This module is the
BOUNDARY ADAPTER for it: it reads a request document, asks the active pack for
`LeakEvidence` exactly as `governance.check` always has, and emits a verdict
document. No predicate logic is added, removed, or reordered here — the decision
is still "block on ``is_solution OR prose_disclosure``, and only under the peer
stance", which is what core governance has always decided.

WHAT DOES NOT CROSS THE BOUNDARY (SPEC.md §10). `LeakEvidence` carries two
candidate-derived surfaces that MUST stay in Belay:

  - ``snippets``         — the extracted code candidates. Verbatim candidate text.
                           Only its LENGTH crosses, as ``snippet_count``.
  - ``redacted_message`` — the draft with code stripped. Still candidate text, and
                           a redaction is a remediation rather than a verdict. It
                           stays with ``governance.safe_rewrite``, its only caller.

Emitting either would put the leaking text into the verdict — and therefore into
the trace — through the contract, which is worse than doing it directly because
it would look like conformance. See SPEC.md §6.1 and `screen_passages`'s
docstring: "its text is never returned here and must never be written to the
trace."

Also not crossing: ``flag: redirect_answer_seeking`` and ``flag: flag_escalate``
are pedagogical routing signals, not judgements about the candidate, and
``block`` is Belay's action rather than the contract's verdict. All three stay in
`governance.check`.

FAN-OUT IS THE CALLER'S (SPEC.md §9). This module verifies exactly one candidate
per call. `governance.screen_passages` loops over passages and calls it once each;
it is deliberately NOT a second profile and NOT a second reason code, because
`screen_passages` exists precisely so there is no parallel passage screen.

This file is also a conformant executable: `python -m app.agent.leak_profile`
reads a request document on stdin, writes a verdict document on stdout, and exits
non-zero if it cannot reach a verdict (SPEC.md §1.1).
"""

from __future__ import annotations

import json
import sys
from typing import Any

PROFILE = "leak"

# Signal order is FIXED. It is the evidence order (SPEC.md §8 makes evidence order
# part of the determinism guarantee) and it is the reason-code precedence (SPEC.md
# §4.1): `is_solution` outranks `prose_disclosure`. This is the same precedence
# `screen_passages` has always used —
# ``"is_solution" if ev.is_solution else "prose_disclosure"``.
_SIGNALS: tuple[tuple[str, str, str], ...] = (
    (
        "is_solution",
        "leak.is_solution",
        "candidate contains code that independently meets the exercise goal",
    ),
    (
        "prose_disclosure",
        "leak.prose_disclosure",
        "candidate prose discloses the solution",
    ),
)


def build_request(
    candidate: str,
    exercise: dict,
    stance: str = "peer",
    subject_id: str | None = None,
) -> dict[str, Any]:
    """Assemble a contract request document for the leak profile.

    The mapping, which is the whole of the port:
      ``draft["message"]``      -> ``candidate``
      ``ctx["_exercise_full"]`` -> ``context.exercise``
      ``stance``                -> ``context.stance``

    ``task`` is the exercise's goal statement: what the candidate was supposed to
    do. The leak predicate ignores it (it judges against the pack's oracle, not
    against prose), but the contract requires the field, and a verdict record that
    does not say what the task was is not much of a record.

    ``context.subject_id`` is the caller's handle on WHICH subject this is, for
    fan-out (SPEC.md §6.2). It is caller-minted and the profile only echoes it —
    it is how a passage drop can be identified without the passage text coming
    back.
    """
    context: dict[str, Any] = {"exercise": exercise, "stance": stance}
    if subject_id is not None:
        context["subject_id"] = subject_id
    return {
        "profile": PROFILE,
        "task": str(exercise.get("goalText", "") or ""),
        "candidate": candidate,
        "context": context,
    }


def _verdict(
    outcome: str,
    reason_code: str | None,
    detail: str,
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    doc: dict[str, Any] = {"verdict": outcome, "profile": PROFILE}
    if reason_code is not None:
        doc["reason_code"] = reason_code
    doc["detail"] = detail
    doc["evidence"] = evidence
    return doc


def verify(request: dict[str, Any], pack=None) -> dict[str, Any]:
    """Request document in, verdict document out. One candidate per call.

    The internal logic is `governance.check`'s leak block, unchanged:

      * only the peer stance is gated — "Oracle stance is explicitly allowed to
        hand over the solution", so a non-peer request passes WITHOUT consulting
        the pack, exactly as the old ``if stance == "peer":`` guard skipped the
        evidence call entirely;
      * the evidence is the pack's (``pack.leak_evidence``), the decision is
        core's;
      * fail on ``is_solution OR prose_disclosure``.
    """
    if pack is None:
        from ..core.registry import get_active_pack

        pack = get_active_pack()

    context = request.get("context") or {}
    stance = context.get("stance", "peer")
    exercise = context.get("exercise") or {}
    subject_id = context.get("subject_id")
    candidate = request.get("candidate", "")

    if stance != "peer":
        # Not a leak-free candidate — a candidate the gate does not apply to. The
        # pack is never consulted, matching the pre-port control flow byte for byte.
        return _verdict(
            "pass",
            None,
            f"stance {stance!r} is not gated; the leak profile withholds only under the peer stance",
            [],
        )

    ev = pack.leak_evidence(candidate, exercise)
    fired = {"is_solution": bool(ev.is_solution), "prose_disclosure": bool(ev.prose_disclosure)}

    # One evidence object per signal EVALUATED, not per signal that fired, in the
    # fixed order above. A pass therefore reports what was checked and found clean,
    # which is what makes coverage measurable instead of assumed (SPEC.md §4).
    # Nothing here is candidate-derived except `snippet_count`, which is a count.
    evidence: list[dict[str, Any]] = [
        {
            "signal": name,
            "fired": fired[name],
            "subject_id": subject_id,
            "snippet_count": len(ev.snippets),
        }
        for name, _code, _detail in _SIGNALS
    ]

    hits = [(code, detail) for name, code, detail in _SIGNALS if fired[name]]
    if not hits:
        return _verdict("pass", None, "no leak signal fired", evidence)

    # `reason_code` is singular and names the PRIMARY reason under the fixed
    # precedence; `detail` and `evidence` carry every signal that fired, so a
    # caller that needs the conjunction loses nothing (SPEC.md §4.1).
    return _verdict("fail", hits[0][0], "; ".join(d for _c, d in hits), evidence)


def main(argv: list[str] | None = None) -> int:
    """Executable form: stdin -> stdout, exit 0 iff a verdict was reached.

    A verifier that cannot decide must exit non-zero rather than emit a `fail`;
    collapsing the two would turn every crashed verifier into a universal failure
    signal (SPEC.md §1.1, §2.2).
    """
    try:
        request = json.loads(sys.stdin.read())
    except (ValueError, OSError) as err:
        print(f"leak: cannot read a request document on stdin: {err}", file=sys.stderr)
        return 2
    try:
        verdict = verify(request)
    except Exception as err:  # noqa: BLE001 — any failure here is a JUDGE failure
        print(f"leak: the verifier failed and reached no verdict: {err!r}", file=sys.stderr)
        return 3
    json.dump(verdict, sys.stdout, sort_keys=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
