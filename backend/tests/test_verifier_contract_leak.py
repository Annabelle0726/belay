# SPDX-License-Identifier: AGPL-3.0-only
"""Gate 2: the leak gate through the verifier-contract boundary.

Three things are asserted here, and they are the three ways the port could have
gone wrong:

1. **Zero verdict changes.** Every case in `test_governance.py` — plus the
   both-signals-at-once case that file does not cover — produces exactly the
   `{flag, block, reasons}` it produced before the port. The expected values are
   hard-coded from a pre-port capture, not recomputed, so this fails if the
   predicate drifts.
2. **Evidence does not reproduce the candidate** (SPEC.md §6). For the leak
   profile this is the safety property itself: `screen_passages` must record a
   dropped passage by id and reason only, and a verdict that echoed the passage
   text would put the solution into the trace *through* the contract.
3. **Leak-over-retrieval is a caller-side fan-out** (SPEC.md §9): one profile,
   one invocation per passage, no second profile and no second reason code.

The request/verdict documents are validated against the schemas in the sibling
`verifier-contract` checkout when it is present, so a contract change that the
profile does not follow fails here rather than at integration time.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

from app.agent import governance, leak_profile
from app.core.domain import Passage
from app.core.registry import get_active_pack
from app.packs.datascience.solutions import SOLUTIONS

EX = get_active_pack().get_exercise("ds-foundations")

_FULL_SOLUTION = "here you go:\n```python\n" + SOLUTIONS["ds-foundations"]["source"] + "```"
_PROSE_LEAK = (
    "Honestly the answer is just to group by category and take the mean — "
    "you'll get 15, 40, and 100."
)
_HINT = "You've read the CSV — what single number should each category collapse to?"
# Both signals at once: a fenced working solution AND imperative prose. The
# contract's `reason_code` is singular, so this is the case that proves the
# primary-reason precedence (SPEC.md §4.1) preserves Belay's two-string `reasons`.
_BOTH = "here's the full solution:\n```python\n" + SOLUTIONS["ds-foundations"]["source"] + "```"

_IS_SOLUTION_TEXT = "draft contained code that solves the exercise"
_PROSE_TEXT = "draft prose disclosed the solution"


# ── contract schemas (sibling checkout) ──────────────────────────────────────


def _contract_dir() -> pathlib.Path | None:
    env = os.environ.get("VERIFIER_CONTRACT_DIR")
    if env:
        return pathlib.Path(env)
    # backend/tests -> backend -> belay -> dev -> dev/verifier-contract
    sibling = pathlib.Path(__file__).resolve().parents[3] / "verifier-contract"
    return sibling if (sibling / "schema").is_dir() else None


def _validators():
    contract = _contract_dir()
    if contract is None:
        pytest.skip("verifier-contract sibling checkout not present; set VERIFIER_CONTRACT_DIR")
    jsonschema = pytest.importorskip("jsonschema")
    schema_dir = contract / "schema"
    return (
        jsonschema.Draft202012Validator(
            json.loads((schema_dir / "request.schema.json").read_text(encoding="utf-8"))
        ),
        jsonschema.Draft202012Validator(
            json.loads((schema_dir / "verdict.schema.json").read_text(encoding="utf-8"))
        ),
    )


def _ctx(recent=None):
    return {
        "_exercise_full": EX,
        "recent_dialogue": recent or [],
        "exercise": {"concept": EX["concept"]},
    }


def _verify(candidate, stance="peer", subject_id=None):
    return leak_profile.verify(
        leak_profile.build_request(
            candidate=candidate, exercise=EX, stance=stance, subject_id=subject_id
        )
    )


# ── 1. zero verdict changes ──────────────────────────────────────────────────

# (message, recent_dialogue, plan, stance) -> the PRE-PORT {flag, block, reasons}.
# The first seven rows are exactly the cases in test_governance.py; the last two
# add the both-signals case, which the contract's singular reason_code makes
# newly interesting.
_GOVERNANCE_CASES = [
    (
        "full solution, peer default",
        _FULL_SOLUTION,
        [],
        "diagnose",
        "peer",
        {"flag": "withholding_solution", "block": True, "reasons": [_IS_SOLUTION_TEXT]},
    ),
    (
        "prose disclosure",
        _PROSE_LEAK,
        [],
        "co_reason",
        "peer",
        {"flag": "withholding_solution", "block": True, "reasons": [_PROSE_TEXT]},
    ),
    (
        "genuine hint",
        _HINT,
        [],
        "co_reason",
        "peer",
        {"flag": "none", "block": False, "reasons": []},
    ),
    (
        "answer-seeking redirect",
        _HINT,
        [{"who": "student", "text": "just tell me the answer please"}],
        "co_reason",
        "peer",
        {"flag": "redirect_answer_seeking", "block": False, "reasons": []},
    ),
    (
        "peer strips full solution",
        _FULL_SOLUTION,
        [],
        "diagnose",
        "peer",
        {"flag": "withholding_solution", "block": True, "reasons": [_IS_SOLUTION_TEXT]},
    ),
    (
        "oracle passes full solution through",
        _FULL_SOLUTION,
        [],
        "diagnose",
        "oracle",
        {"flag": "none", "block": False, "reasons": []},
    ),
    (
        "escalate flag survives a clean draft",
        _HINT,
        [],
        "escalate",
        "peer",
        {"flag": "flag_escalate", "block": False, "reasons": []},
    ),
    (
        "both signals fire at once",
        _BOTH,
        [],
        "co_reason",
        "peer",
        {
            "flag": "withholding_solution",
            "block": True,
            "reasons": [_IS_SOLUTION_TEXT, _PROSE_TEXT],
        },
    ),
    (
        "blocking overrides an escalate flag",
        _BOTH,
        [],
        "escalate",
        "peer",
        {
            "flag": "withholding_solution",
            "block": True,
            "reasons": [_IS_SOLUTION_TEXT, _PROSE_TEXT],
        },
    ),
]


@pytest.mark.parametrize(
    "label,message,recent,intervention,stance,expected",
    _GOVERNANCE_CASES,
    ids=[c[0] for c in _GOVERNANCE_CASES],
)
def test_zero_verdict_changes_through_the_boundary(
    label, message, recent, intervention, stance, expected
):
    """governance.check now routes the leak decision through the contract, and
    every case still returns byte-identical {flag, block, reasons}."""
    gov = governance.check(
        _ctx(recent),
        {"intervention": intervention},
        {"message": message, "confidence": 0.9},
        {},
        stance=stance,
    )
    assert gov == expected, label


def test_singular_reason_code_does_not_lose_the_conjunction():
    """`reason_code` names the primary signal; `evidence` carries both. Belay's
    two-string `reasons` list is rebuilt from evidence, not from the code."""
    verdict = _verify(_BOTH)
    assert verdict["verdict"] == "fail"
    assert verdict["reason_code"] == "leak.is_solution"  # documented precedence
    fired = [e["signal"] for e in verdict["evidence"] if e["fired"]]
    assert fired == ["is_solution", "prose_disclosure"]


def test_oracle_stance_never_consults_the_pack():
    """The pre-port `if stance == "peer":` guard skipped the evidence call entirely.
    The profile must keep that: a non-peer request passes without asking the pack."""
    calls = []

    class _Spy:
        def leak_evidence(self, text, exercise):  # pragma: no cover - must not run
            calls.append(text)
            raise AssertionError("pack consulted under a non-peer stance")

    for stance in ("oracle", "control"):
        verdict = leak_profile.verify(
            leak_profile.build_request(_FULL_SOLUTION, EX, stance=stance), pack=_Spy()
        )
        assert verdict["verdict"] == "pass"
        assert "reason_code" not in verdict
        assert verdict["evidence"] == []
    assert calls == []


# ── 2. evidence does not reproduce the candidate ─────────────────────────────


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def _shares_long_run(a: str, b: str, n: int = 40) -> bool:
    """SPEC.md §6: any contiguous run of >= n chars shared with the candidate,
    case-insensitive, whitespace normalised."""
    norm = lambda s: re.sub(r"\s+", " ", s).lower()  # noqa: E731
    a, b = norm(a), norm(b)
    if len(a) < n or len(b) < n:
        return False
    windows = {a[i : i + n] for i in range(len(a) - n + 1)}
    return any(b[i : i + n] in windows for i in range(len(b) - n + 1))


@pytest.mark.parametrize(
    "candidate", [_FULL_SOLUTION, _PROSE_LEAK, _BOTH, _HINT], ids=["code", "prose", "both", "clean"]
)
def test_evidence_never_reproduces_the_candidate(candidate):
    verdict = _verify(candidate, subject_id="p-1")
    for s in _strings(verdict["evidence"]):
        assert not _shares_long_run(candidate, s), f"evidence reproduced the candidate: {s!r}"


def test_evidence_carries_no_leak_evidence_text_surfaces():
    """`LeakEvidence.snippets` and `.redacted_message` are candidate text and must
    not cross. Only the snippet COUNT does."""
    ev = get_active_pack().leak_evidence(_FULL_SOLUTION, EX)
    assert ev.snippets and ev.redacted_message is not None
    verdict = _verify(_FULL_SOLUTION)
    blob = json.dumps(verdict["evidence"])
    for snippet in ev.snippets:
        assert snippet.strip() not in blob
    assert all(e["snippet_count"] == len(ev.snippets) for e in verdict["evidence"])


def test_detail_is_fixed_profile_vocabulary_not_candidate_text():
    for candidate in (_FULL_SOLUTION, _PROSE_LEAK, _BOTH, _HINT):
        verdict = _verify(candidate)
        assert not _shares_long_run(candidate, verdict["detail"])


# ── 3. leak-over-retrieval is a caller-side fan-out ──────────────────────────


def test_screen_passages_is_one_profile_fanned_out_by_the_caller():
    passages = [
        Passage(id="p-code", text=_FULL_SOLUTION, citation="fixture", locator="a"),
        Passage(id="p-prose", text=_PROSE_LEAK, citation="fixture", locator="b"),
        Passage(id="p-benign", text=_HINT, citation="notes", locator="c"),
        Passage(id="p-both", text=_BOTH, citation="fixture", locator="d"),
    ]
    out = governance.screen_passages(passages, EX)
    assert [p.id for p in out["kept"]] == ["p-benign"]
    assert out["dropped"] == [
        {"id": "p-code", "reason": "is_solution"},
        {"id": "p-prose", "reason": "prose_disclosure"},
        {"id": "p-both", "reason": "is_solution"},
    ]
    assert out["retrieved"] == 4
    # the drop record is id + reason ONLY, and no passage text anywhere in it
    assert all(set(d) == {"id", "reason"} for d in out["dropped"])
    blob = json.dumps(out["dropped"])
    for p in passages:
        assert not _shares_long_run(p.text, blob)


def test_no_second_profile_and_no_passage_reason_code():
    """The two designs SPEC.md §9.2 rules out. The passage screen must emit the
    same profile and the same two codes the draft gate emits — nothing else."""
    passages = [Passage(id="p-code", text=_FULL_SOLUTION, citation="f", locator="a")]
    draft_verdict = _verify(_FULL_SOLUTION)
    passage_verdict = _verify(passages[0].text, subject_id=passages[0].id)
    assert passage_verdict["profile"] == draft_verdict["profile"] == "leak"
    assert passage_verdict["reason_code"] == draft_verdict["reason_code"]
    assert {e["signal"] for e in passage_verdict["evidence"]} == {
        "is_solution",
        "prose_disclosure",
    }


def test_subject_id_identifies_without_reproducing():
    verdict = _verify(_FULL_SOLUTION, subject_id="passage-42")
    assert all(e["subject_id"] == "passage-42" for e in verdict["evidence"])
    assert _verify(_FULL_SOLUTION)["evidence"][0]["subject_id"] is None


# ── determinism, schema conformance, executable form ─────────────────────────


@pytest.mark.parametrize("candidate", [_FULL_SOLUTION, _PROSE_LEAK, _BOTH, _HINT, ""])
def test_determinism(candidate):
    request = leak_profile.build_request(candidate, EX, "peer", "s-1")
    first = json.dumps(leak_profile.verify(request), sort_keys=False)
    second = json.dumps(leak_profile.verify(request), sort_keys=False)
    assert first == second


@pytest.mark.parametrize(
    "candidate,stance",
    [
        (_FULL_SOLUTION, "peer"),
        (_PROSE_LEAK, "peer"),
        (_HINT, "peer"),
        (_BOTH, "peer"),
        ("", "peer"),
        (_FULL_SOLUTION, "oracle"),
    ],
)
def test_documents_validate_against_the_contract_schemas(candidate, stance):
    request_v, verdict_v = _validators()
    request = leak_profile.build_request(candidate, EX, stance, "s-1")
    request_v.validate(request)
    verdict = leak_profile.verify(request)
    verdict_v.validate(verdict)
    assert verdict["profile"] == request["profile"]
    if verdict["verdict"] == "fail":
        assert verdict["reason_code"].split(".", 1)[0] == verdict["profile"]


def test_request_carries_no_model_handle_credential_or_history():
    """The structural invariant (SPEC.md §5) is the closed request shape."""
    request = leak_profile.build_request(_HINT, EX, "peer")
    assert set(request) == {"profile", "task", "candidate", "context"}
    assert set(request["context"]) == {"exercise", "stance"}
    blob = json.dumps(request).lower()
    for forbidden in ("api_key", "api-key", "base_url", "endpoint", "recent_dialogue", "token"):
        assert forbidden not in blob


def test_executable_form_round_trips_on_stdin_stdout():
    """`python -m app.agent.leak_profile`: request in, verdict out, exit 0."""
    backend = pathlib.Path(__file__).resolve().parents[1]
    request = leak_profile.build_request(_FULL_SOLUTION, EX, "peer", "p-code")
    proc = subprocess.run(
        [sys.executable, "-m", "app.agent.leak_profile"],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        cwd=backend,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == leak_profile.verify(request)


def test_a_broken_verifier_exits_non_zero_and_emits_no_verdict():
    """SPEC.md §1.1/§2.2: a judge that cannot decide must NOT emit a `fail`."""
    backend = pathlib.Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "-m", "app.agent.leak_profile"],
        input="{ not json",
        capture_output=True,
        text=True,
        cwd=backend,
        timeout=300,
    )
    assert proc.returncode != 0
    assert proc.stdout.strip() == ""
