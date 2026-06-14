"""
Process-measure unit tests (pure offline, no LLM/network).

Each test class owns a focused synthetic trace for exactly the case being
exercised. The Bell exercise (target {"00":0.5,"11":0.5}, tol=0.07) is used
throughout because the full solution is deterministic and short.

Synthetic event layout:
  make_run(ts, source, tvd, goal_met)  → run event dict
  make_turn(ts, **kwargs)              → turn event dict

All ts values are strict ISO strings so ordering comparisons are unambiguous.
"""
from __future__ import annotations

from app.analysis.measures import (
    HANDOFF_WINDOW,
    aggregate_participant,
    attempted_handoff,
    brier_score,
    compute_attempt_measures,
    compute_calibration_pairs,
    compute_learner_model_measures,
    ece,
    nontrivial_revision,
    predicted_leak,
    predicted_leak_strict,
    realized_handoff,
    redirect,
)
from app.curriculum import get_exercise
from app.quantum.backend import LocalSimulator

# ── test fixtures ─────────────────────────────────────────────────────────────

BELL = get_exercise("bell")      # target {"00":0.5,"11":0.5}, tol=0.07
SIM = LocalSimulator()

# Full Bell-pair solution — grader returns goalMet=True
_BELL_SRC = "allocate 2\nsuperpose q0\nentangle q0 q1\nmeasure all"
# Message that contains the Bell solution as op lines (4 consecutive lines → picked up)
_ORACLE_MSG = (
    "Here's the full solution:\n"
    "allocate 2\n"
    "superpose q0\n"
    "entangle q0 q1\n"
    "measure all"
)
# Stripped peer message — no code
_STRIPPED_MSG = "I don't want to paste the whole thing — what's the next step?"


def _ts(n: int) -> str:
    """Simple monotone ts strings: 2026-06-01T00:00:00.000n00+00:00"""
    return f"2026-06-01T00:00:0{n}.000000+00:00"


def make_run(
    n: int,
    source: str = _BELL_SRC,
    tvd: float = 0.5,
    goal_met: bool = False,
    dist=None,
    ok: bool = True,
    error: str = "",
) -> dict:
    if dist is None:
        dist = [{"bits": "00", "p": round(1 - tvd, 2)}, {"bits": "10", "p": round(tvd, 2)}]
    result = (
        {"ok": True, "tvd": tvd, "goalMet": goal_met, "dist": dist}
        if ok
        else {"ok": False, "error": error}
    )
    return {
        "participant_id": "p_test",
        "exercise_id": "bell",
        "event_type": "run",
        "ts": _ts(n),
        "stance": None,
        "payload": {"source": source, "result": result},
        "note": "",
    }


def make_turn(
    n: int,
    pid: str = "p_test",
    stance: str = "peer",
    intervention: str = "co_reason",
    plan_confidence: float = 0.7,
    se_confidence: float = 0.75,
    leak_risk: str = "none",
    needs_revision: bool = False,
    gov_flag: str = "none",
    gov_block: bool = False,
    escalated: bool = False,
    abstained: bool = False,
    final_message: str = _STRIPPED_MSG,
    reasoning_effort: str = "medium",
) -> dict:
    return {
        "participant_id": pid,
        "exercise_id": "bell",
        "event_type": "turn",
        "ts": _ts(n),
        "stance": stance,
        "payload": {
            "stance": stance,
            "plan": {
                "intervention": intervention,
                "confidence": plan_confidence,
                "target_concept": "entanglement",
            },
            "self_eval": {
                "confidence": se_confidence,
                "leak_risk": leak_risk,
                "needs_revision": needs_revision,
            },
            "governance": {
                "flag": gov_flag,
                "block": gov_block,
                "reasons": [],
            },
            "telemetry": {
                "escalated": escalated,
                "abstained": abstained,
                "reasoning_effort": reasoning_effort,
                "confidence_trajectory": {
                    "planner": plan_confidence,
                    "reasoner": 0.80,
                    "self_eval": se_confidence,
                },
            },
            "final_message": final_message,
        },
        "note": "",
    }


# ── §2 realized vs stripped hand-off ─────────────────────────────────────────

class TestHandoffs:
    def test_oracle_realized_handoff_true(self):
        """Oracle final_message with the Bell solution → realized_handoff=True."""
        t = make_turn(0, stance="oracle", final_message=_ORACLE_MSG)
        assert realized_handoff(t, BELL["target"], BELL["tol"], SIM) is True

    def test_peer_stripped_realized_handoff_false(self):
        """Stripped peer message with no code → realized_handoff=False."""
        t = make_turn(0, stance="peer", final_message=_STRIPPED_MSG,
                      gov_flag="withholding_solution", gov_block=True)
        assert realized_handoff(t, BELL["target"], BELL["tol"], SIM) is False

    def test_peer_attempted_handoff(self):
        """Peer turn flagged withholding_solution → attempted_handoff=True."""
        t = make_turn(0, gov_flag="withholding_solution", gov_block=True)
        assert attempted_handoff(t) is True

    def test_oracle_no_attempted_handoff(self):
        """Oracle turn with flag=none → attempted_handoff=False."""
        t = make_turn(0, stance="oracle", gov_flag="none")
        assert attempted_handoff(t) is False

    def test_attempt_measures_handoff_counts(self):
        """compute_attempt_measures counts handoffs correctly for both arms."""
        oracle_turn = make_turn(1, stance="oracle", final_message=_ORACLE_MSG)
        peer_turn = make_turn(2, stance="peer", final_message=_STRIPPED_MSG,
                              gov_flag="withholding_solution", gov_block=True)
        run1 = make_run(0, tvd=0.5)
        events = [run1, oracle_turn, peer_turn]
        m = compute_attempt_measures("p_test", "bell", events, BELL, SIM)
        assert m["realized_handoff_count"] == 1    # oracle
        assert m["attempted_handoff_count"] == 1   # peer
        assert m["realized_handoff_rate"] == 0.5   # 1 of 2 turns


# ── §3 redirects ─────────────────────────────────────────────────────────────

class TestRedirects:
    def test_peer_redirect_flag(self):
        t = make_turn(0, gov_flag="redirect_answer_seeking")
        assert redirect(t) is True

    def test_oracle_no_redirect(self):
        """Oracle answers answer-seeking → flag=none → redirect=False."""
        t = make_turn(0, stance="oracle", gov_flag="none",
                      final_message="Here is the answer: " + _BELL_SRC)
        assert redirect(t) is False

    def test_redirect_rate(self):
        t1 = make_turn(1, gov_flag="redirect_answer_seeking")
        t2 = make_turn(2, gov_flag="none")
        run1 = make_run(0, tvd=0.5)
        events = [run1, t1, t2]
        m = compute_attempt_measures("p_test", "bell", events, BELL, SIM)
        assert m["redirect_count"] == 1
        assert m["redirect_rate"] == 0.5


# ── §4a leak calibration ─────────────────────────────────────────────────────

class TestLeakCalibration:
    def test_predicted_partial_or_full(self):
        t_partial = make_turn(0, leak_risk="partial")
        t_full = make_turn(1, leak_risk="full")
        t_none = make_turn(2, leak_risk="none")
        assert predicted_leak(t_partial) is True
        assert predicted_leak(t_full) is True
        assert predicted_leak(t_none) is False

    def test_predicted_strict_full_only(self):
        assert predicted_leak_strict(make_turn(0, leak_risk="partial")) is False
        assert predicted_leak_strict(make_turn(0, leak_risk="full")) is True
        assert predicted_leak_strict(make_turn(0, leak_risk="none")) is False

    def test_leak_match_tp(self):
        """predicted=partial AND actual=withholding → TP, miss_rate=0."""
        t = make_turn(1, leak_risk="partial", gov_flag="withholding_solution", gov_block=True)
        run = make_run(0, tvd=0.5)
        events = [run, t]
        m = compute_attempt_measures("p_test", "bell", events, BELL, SIM)
        assert m["leak_tp"] == 1
        assert m["leak_fn"] == 0
        assert m["leak_miss_rate"] == 0.0

    def test_leak_miss_fn(self):
        """predicted=none AND actual=withholding → FN, miss_rate=1.0."""
        t = make_turn(1, leak_risk="none", gov_flag="withholding_solution", gov_block=True)
        run = make_run(0, tvd=0.5)
        events = [run, t]
        m = compute_attempt_measures("p_test", "bell", events, BELL, SIM)
        assert m["leak_fn"] == 1
        assert m["leak_tp"] == 0
        assert m["leak_miss_rate"] == 1.0


# ── §4b guidance calibration ─────────────────────────────────────────────────

class TestGuidanceCalibration:
    """window=2; confident turn followed by a progress run → outcome=True."""

    def _make_trace(self, with_progress: bool):
        # Run 0: tvd=0.8
        # Turn 1: guidance (co_reason), confidence=0.75
        # Run 2: tvd=0.3 if with_progress else tvd=0.8 (same)
        # Run 3: tvd=0.1 if with_progress else tvd=0.8
        run0 = make_run(0, tvd=0.8)
        turn1 = make_turn(1, intervention="co_reason", se_confidence=0.75)
        if with_progress:
            run2 = make_run(2, tvd=0.3)
            run3 = make_run(3, tvd=0.0, goal_met=True,
                            dist=[{"bits": "00", "p": 0.5}, {"bits": "11", "p": 0.5}])
        else:
            run2 = make_run(2, tvd=0.8,
                            dist=[{"bits": "00", "p": 0.5}, {"bits": "10", "p": 0.5}])
            run3 = make_run(3, tvd=0.8,
                            dist=[{"bits": "00", "p": 0.5}, {"bits": "10", "p": 0.5}])
        return [run0, turn1, run2, run3]

    def test_confident_with_progress(self):
        events = self._make_trace(with_progress=True)
        pairs = compute_calibration_pairs("p_test", "bell", events, BELL, SIM)
        assert len(pairs) == 1
        assert pairs[0]["outcome"] == 1
        assert pairs[0]["confidence"] == 0.75

    def test_confident_no_progress(self):
        events = self._make_trace(with_progress=False)
        pairs = compute_calibration_pairs("p_test", "bell", events, BELL, SIM)
        assert len(pairs) == 1
        assert pairs[0]["outcome"] == 0

    def test_observe_excluded_from_outcome(self):
        """observe turns must not produce an outcome (no §4b pair)."""
        run0 = make_run(0, tvd=0.5)
        turn_obs = make_turn(1, intervention="observe", se_confidence=0.9)
        run1 = make_run(2, tvd=0.0, goal_met=True,
                        dist=[{"bits": "00", "p": 0.5}, {"bits": "11", "p": 0.5}])
        events = [run0, turn_obs, run1]
        pairs = compute_calibration_pairs("p_test", "bell", events, BELL, SIM)
        assert all(p["outcome"] is None for p in pairs)

    def test_no_subsequent_run_no_outcome(self):
        """Turn with no run after it → outcome=None (§7 edge case)."""
        run0 = make_run(0, tvd=0.5)
        turn1 = make_turn(1, intervention="co_reason", se_confidence=0.8)
        events = [run0, turn1]
        pairs = compute_calibration_pairs("p_test", "bell", events, BELL, SIM)
        assert pairs[0]["outcome"] is None


# ── §4c abstention calibration ────────────────────────────────────────────────

class TestAbstentionCalibration:
    def test_abstained_no_progress_precision_1(self):
        """Single abstained turn; no subsequent progress → abstention_precision=1."""
        run0 = make_run(0, tvd=0.8)
        turn_ab = make_turn(
            1, gov_flag="flag_escalate", se_confidence=0.2,
            escalated=True, abstained=True,
            final_message="Honestly I'm not sure...",
        )
        run1 = make_run(2, tvd=0.8,  # no improvement
                        dist=[{"bits": "00", "p": 0.5}, {"bits": "10", "p": 0.5}])
        events = [run0, turn_ab, run1]
        m = compute_attempt_measures("p_test", "bell", events, BELL, SIM)
        assert m["n_abstained"] == 1
        assert m["abstention_precision"] == 1.0
        assert m["false_abstention_rate"] == 0.0

    def test_abstained_with_progress_false_abstention(self):
        """Two abstained turns: one with no progress (correct), one with progress (false).

        turn_ab1 window (size 2) covers run1 + run2 — both no-progress → correct.
        turn_ab2 window covers run3 — progress → false abstention.
        """
        run0 = make_run(0, tvd=0.8)
        turn_ab1 = make_turn(1, gov_flag="flag_escalate", se_confidence=0.2,
                             escalated=True, abstained=True)
        run1 = make_run(2, tvd=0.8,    # window slot 1 for turn_ab1: no progress
                        dist=[{"bits": "00", "p": 0.5}, {"bits": "10", "p": 0.5}])
        run2 = make_run(3, tvd=0.8,    # window slot 2 for turn_ab1: no progress
                        dist=[{"bits": "00", "p": 0.5}, {"bits": "10", "p": 0.5}])
        turn_ab2 = make_turn(4, gov_flag="flag_escalate", se_confidence=0.2,
                             escalated=True, abstained=True)
        run3 = make_run(5, tvd=0.3)   # window slot 1 for turn_ab2: progress → false abstention
        events = [run0, turn_ab1, run1, run2, turn_ab2, run3]
        m = compute_attempt_measures("p_test", "bell", events, BELL, SIM)
        assert m["n_abstained"] == 2
        assert m["abstention_precision"] == 0.5
        assert m["false_abstention_rate"] == 0.5


# ── §5 struggle markers ───────────────────────────────────────────────────────

_SRC_SUPERPOSE = "allocate 2\nsuperpose q0\nmeasure all"
_SRC_ENTANGLE = "allocate 2\nsuperpose q0\nentangle q0 q1\nmeasure all"
_BELL_DIST = [{"bits": "00", "p": 0.5}, {"bits": "11", "p": 0.5}]
_STUCK_DIST = [{"bits": "00", "p": 0.5}, {"bits": "10", "p": 0.5}]


class TestStruggle:
    def test_productive_span(self):
        """TVD decreasing over ≥2 attempts, eventual solve → span_class=productive."""
        runs = [
            make_run(0, source=_SRC_SUPERPOSE, tvd=0.5),
            make_run(2, source=_SRC_ENTANGLE, tvd=0.0, goal_met=True, dist=_BELL_DIST),
        ]
        turn = make_turn(1)
        events = [runs[0], turn, runs[1]]
        m = compute_attempt_measures("p_test", "bell", events, BELL, SIM)
        assert m["solved"] is True
        assert m["attempts_to_solve"] == 1   # 1 run before the solving run
        assert m["tvd_slope"] is not None
        assert m["tvd_slope"] < 0
        assert m["span_class"] == "productive"

    def test_unproductive_stuck_span(self):
        """≥3 attempts, no progress, repeated error signature → unproductive_stuck."""
        runs = [
            make_run(0, source=_SRC_SUPERPOSE, tvd=0.5, dist=_STUCK_DIST),
            make_run(2, source=_SRC_SUPERPOSE, tvd=0.5, dist=_STUCK_DIST),
            make_run(4, source=_SRC_SUPERPOSE, tvd=0.5, dist=_STUCK_DIST),
        ]
        turns = [make_turn(1), make_turn(3)]
        events = sorted([*runs, *turns], key=lambda e: e["ts"])
        m = compute_attempt_measures("p_test", "bell", events, BELL, SIM)
        assert m["solved"] is False
        assert m["repeated_error_count"] >= 1
        assert m["span_class"] == "unproductive_stuck"

    def test_attempts_to_solve_count(self):
        """attempts_to_solve = run events BEFORE solved_at (not counting the solve)."""
        runs = [
            make_run(0, tvd=0.5),
            make_run(1, tvd=0.3),
            make_run(2, tvd=0.0, goal_met=True, dist=_BELL_DIST),
        ]
        m = compute_attempt_measures("p_test", "bell", runs, BELL, SIM)
        assert m["solved"] is True
        assert m["attempts_to_solve"] == 2   # runs[0] and runs[1] precede the solve


# ── §5 op-level revision ─────────────────────────────────────────────────────

class TestNontrivialRevision:
    def test_op_added_is_nontrivial(self):
        """Adding entangle to a superpose-only submission → nontrivial."""
        assert nontrivial_revision(_SRC_SUPERPOSE, _SRC_ENTANGLE) is True

    def test_whitespace_only_change_is_trivial(self):
        """Adding a comment or blank line with the same ops → trivial."""
        src_with_comment = "allocate 2\n# this is a comment\nsuperpose q0\nmeasure all"
        assert nontrivial_revision(_SRC_SUPERPOSE, src_with_comment) is False

    def test_identical_submission_trivial(self):
        assert nontrivial_revision(_SRC_SUPERPOSE, _SRC_SUPERPOSE) is False

    def test_revision_count_in_measures(self):
        """Run sequence A → A+comment (trivial) → A+entangle (nontrivial) → count=1."""
        src_comment = "allocate 2\n# note\nsuperpose q0\nmeasure all"
        runs = [
            make_run(0, source=_SRC_SUPERPOSE, tvd=0.5),
            make_run(1, source=src_comment, tvd=0.5),
            make_run(2, source=_SRC_ENTANGLE, tvd=0.0, goal_met=True, dist=_BELL_DIST),
        ]
        m = compute_attempt_measures("p_test", "bell", runs, BELL, SIM)
        assert m["nontrivial_revision_count"] == 1   # only A+entangle step


# ── §5b escalation rate ───────────────────────────────────────────────────────

class TestEscalationRate:
    def _make_turns(self, escalated_flags):
        return [
            make_turn(i, escalated=flag)
            for i, flag in enumerate(escalated_flags)
        ]

    def test_escalation_rate_per_arm(self):
        """escalation_rate = escalated / total; correctly split by stance."""
        peer_turns = [
            make_turn(0, stance="peer", escalated=True),
            make_turn(1, stance="peer", escalated=False),
        ]
        oracle_turns = [
            make_turn(2, stance="oracle", escalated=True),
        ]
        run0 = make_run(3, tvd=0.5)

        # peer attempt
        peer_events = [*peer_turns, run0]
        m_peer = compute_attempt_measures("p_peer", "bell", peer_events, BELL, SIM)
        assert m_peer["escalation_rate"] == 0.5
        assert m_peer["n_escalated"] == 1

        # oracle attempt
        oracle_events = [*oracle_turns, run0]
        m_oracle = compute_attempt_measures("p_oracle", "bell", oracle_events, BELL, SIM)
        assert m_oracle["escalation_rate"] == 1.0

        # aggregate
        m_peer["participant_id"] = "p_mixed"
        m_peer["stance"] = "peer"
        m_oracle["participant_id"] = "p_mixed"
        m_oracle["stance"] = "oracle"
        agg = aggregate_participant("p_mixed", [m_peer, m_oracle])
        assert agg["escalation_rate_peer"] == 0.5
        assert agg["escalation_rate_oracle"] == 1.0
        assert agg["escalation_rate"] == pytest.approx(2 / 3)

    def test_no_escalations(self):
        turns = self._make_turns([False, False, False])
        run0 = make_run(3, tvd=0.5)
        events = [*turns, run0]
        m = compute_attempt_measures("p_test", "bell", events, BELL, SIM)
        assert m["escalation_rate"] == 0.0
        assert m["n_escalated"] == 0


# ── ECE + Brier sanity checks ────────────────────────────────────────────────

class TestCalibrationStats:
    def test_perfectly_calibrated(self):
        """Perfect calibration: every conf=0.5, half outcomes=1 → ECE≈0."""
        pairs = [(0.5, 1), (0.5, 0), (0.5, 1), (0.5, 0)]
        assert ece(pairs) == pytest.approx(0.0, abs=1e-9)
        assert brier_score(pairs) == pytest.approx(0.25, abs=1e-9)

    def test_overconfident(self):
        """Always predict 1.0, outcomes are 0/1 mix → positive ECE."""
        pairs = [(1.0, 0), (1.0, 0), (1.0, 1)]
        assert ece(pairs) > 0

    def test_empty_returns_zero(self):
        assert ece([]) == 0.0
        assert brier_score([]) == 0.0


import pytest

# ── fix 1: governance gate ↔ realized_handoff identity (shared leak_check) ───

class TestGovernanceGateIdentity:
    """Confirm governance.check and measures.realized_handoff call the same
    function so they can never disagree on a single message."""

    def test_single_line_fenced_snippet_not_extracted(self):
        """A single-line fenced block (no newline after ```) must NOT be
        treated as a solution snippet by either caller.

        The drifted measures.py _FENCE used \\n? (optional newline), which
        would match ```allocate 2``` as a code block.  The canonical FENCE
        (governance / leak_check) requires \\n so it is NOT extracted.
        This test pins that both callers agree: no false positive."""
        from app.agent import governance
        from app.quantum.leak_check import candidate_snippets, is_goal_meeting

        inline_msg = "try this: ```allocate 2```"
        snippets = candidate_snippets(inline_msg)
        assert snippets == [], (
            "inline single-line fence must not be extracted as a snippet"
        )
        assert is_goal_meeting(inline_msg, BELL["target"], BELL["tol"], SIM) is False

    def test_proper_fenced_block_extracted(self):
        """A properly-formatted fenced block (newline after ```) IS extracted."""
        from app.quantum.leak_check import candidate_snippets

        fenced_msg = "```\n" + _BELL_SRC + "\n```"
        snippets = candidate_snippets(fenced_msg)
        # Both the fence regex AND the op-line scanner fire — correct/expected.
        assert len(snippets) >= 1
        assert any("entangle" in s for s in snippets)

    def test_governance_and_realized_handoff_agree_on_solution(self):
        """For a message containing the Bell solution, governance.check blocks it
        (peer) AND realized_handoff returns True — both True from the same check."""
        from app.agent import governance

        msg = _ORACLE_MSG   # 4 consecutive op lines → extracted as solution
        ctx = {
            "_exercise_full": BELL,
            "recent_dialogue": [],
        }
        plan = {"intervention": "diagnose"}
        draft = {"message": msg, "confidence": 0.9}
        gov = governance.check(ctx, plan, draft, {}, stance="peer")
        assert gov["block"] is True
        assert gov["flag"] == "withholding_solution"

        turn = make_turn(0, stance="oracle", final_message=msg)
        assert realized_handoff(turn, BELL["target"], BELL["tol"], SIM) is True

    def test_governance_and_realized_handoff_agree_on_non_solution(self):
        """For a message without code, both report no leak."""
        from app.agent import governance

        msg = "Think about what links the two qubits."
        ctx = {"_exercise_full": BELL, "recent_dialogue": []}
        plan = {"intervention": "co_reason"}
        draft = {"message": msg, "confidence": 0.7}
        gov = governance.check(ctx, plan, draft, {}, stance="peer")
        assert gov["block"] is False

        turn = make_turn(0, stance="peer", final_message=msg)
        assert realized_handoff(turn, BELL["target"], BELL["tol"], SIM) is False


# ── fix 2: compile errors scored as TVD=1.0 (not inf) ────────────────────────

class TestCompileErrorTVD:
    """A run sequence whose first submission fails to compile must yield a
    finite tvd_slope and a correct span_class — not nan from 0 * inf."""

    def _compile_error_run(self, n: int) -> dict:
        return {
            "participant_id": "p_test",
            "exercise_id": "bell",
            "event_type": "run",
            "ts": _ts(n),
            "stance": None,
            "payload": {
                "source": "not valid syntax!!",
                "result": {"ok": False, "error": "Unknown operation 'not'"},
            },
            "note": "",
        }

    def test_tvd_slope_is_finite_after_compile_error(self):
        """compile_error → 1.0, then improving runs → negative finite slope."""
        runs = [
            self._compile_error_run(0),          # tvd = 1.0 (max)
            make_run(1, tvd=0.5),                # improving
            make_run(2, tvd=0.0, goal_met=True, dist=_BELL_DIST),
        ]
        m = compute_attempt_measures("p_test", "bell", runs, BELL, SIM)
        assert m["tvd_slope"] is not None
        assert m["tvd_slope"] == m["tvd_slope"]   # not nan
        assert m["tvd_slope"] < 0                 # decreasing = productive

    def test_span_class_productive_despite_compile_error(self):
        """Compile error followed by a solve → still productive."""
        runs = [
            self._compile_error_run(0),
            make_run(1, tvd=0.5),
            make_run(2, tvd=0.0, goal_met=True, dist=_BELL_DIST),
        ]
        m = compute_attempt_measures("p_test", "bell", runs, BELL, SIM)
        assert m["span_class"] == "productive"
        assert m["solved"] is True

    def test_all_compile_errors_slope_is_zero(self):
        """All compile errors → all tvd=1.0 → slope=0.0 (flat), not nan."""
        runs = [
            self._compile_error_run(0),
            self._compile_error_run(1),
            self._compile_error_run(2),
        ]
        m = compute_attempt_measures("p_test", "bell", runs, BELL, SIM)
        assert m["tvd_slope"] is not None
        assert m["tvd_slope"] == m["tvd_slope"]   # not nan
        assert m["tvd_slope"] == pytest.approx(0.0, abs=1e-9)
        assert m["span_class"] == "unproductive_stuck"   # ≥3, no progress, repeated error


# ── §5d worked-example verification measures ──────────────────────────────────

def _make_we_turn(n, verified=True, retries=0, stance="peer"):
    """make_turn variant with telemetry.worked_example populated."""
    t = make_turn(n, stance=stance, intervention="worked_analogy")
    t["payload"]["plan"]["affective_state"] = "confusion"
    t["payload"]["telemetry"]["worked_example"] = {
        "verified": verified,
        "reason": "verified" if verified else "prediction_mismatch",
        "retries": retries,
        "shown": verified,
        "claim_ok": True if verified else None,
    }
    return t


class TestWorkedExampleMeasures:
    def test_no_worked_analogy_turns_null_rates(self):
        """No worked_analogy turns → count=0, rates=None."""
        run0 = make_run(0, tvd=0.5)
        t1 = make_turn(1, intervention="co_reason")
        m = compute_attempt_measures("p_test", "bell", [run0, t1], BELL, SIM)
        assert m["worked_example_count"] == 0
        assert m["worked_example_verified_rate"] is None
        assert m["worked_example_retry_rate"] is None

    def test_all_verified_rate_one(self):
        """All worked_analogy examples verified → verified_rate=1.0."""
        run0 = make_run(0, tvd=0.5)
        t1 = _make_we_turn(1, verified=True, retries=0)
        t2 = _make_we_turn(2, verified=True, retries=1)
        m = compute_attempt_measures("p_test", "bell", [run0, t1, t2], BELL, SIM)
        assert m["worked_example_count"] == 2
        assert m["worked_example_verified_rate"] == pytest.approx(1.0)
        assert m["worked_example_retry_rate"] == pytest.approx(0.5)  # mean(0,1)

    def test_partial_verification(self):
        """One verified, one not → verified_rate=0.5."""
        run0 = make_run(0, tvd=0.5)
        t1 = _make_we_turn(1, verified=True, retries=0)
        t2 = _make_we_turn(2, verified=False, retries=1)
        m = compute_attempt_measures("p_test", "bell", [run0, t1, t2], BELL, SIM)
        assert m["worked_example_count"] == 2
        assert m["worked_example_verified_rate"] == pytest.approx(0.5)

    def test_non_we_turn_excluded(self):
        """Turns without worked_example telemetry are excluded from §5d."""
        run0 = make_run(0, tvd=0.5)
        t1 = make_turn(1, intervention="co_reason")   # no we_tel
        t2 = _make_we_turn(2, verified=True, retries=0)
        m = compute_attempt_measures("p_test", "bell", [run0, t1, t2], BELL, SIM)
        assert m["worked_example_count"] == 1
        assert m["worked_example_verified_rate"] == pytest.approx(1.0)

    def test_aggregate_propagates_we_rates(self):
        """aggregate_participant averages §5d rates across attempt rows."""
        row1 = {"participant_id": "px", "stance": "peer", "n_turns": 2,
                "worked_example_count": 1, "worked_example_verified_rate": 1.0,
                "worked_example_retry_rate": 0.0, "n_escalated": 0}
        row2 = {"participant_id": "px", "stance": "peer", "n_turns": 2,
                "worked_example_count": 1, "worked_example_verified_rate": 0.0,
                "worked_example_retry_rate": 1.0, "n_escalated": 0}
        agg = aggregate_participant("px", [row1, row2])
        assert agg["worked_example_count"] == 2
        assert agg["worked_example_verified_rate"] == pytest.approx(0.5)
        assert agg["worked_example_retry_rate"] == pytest.approx(0.5)


# ── §5c affect-response measures ──────────────────────────────────────────────

def _affect_turn(n, affect, intervention="co_reason", stance="peer"):
    """make_turn variant that also writes affective_state into the plan."""
    t = make_turn(n, stance=stance, intervention=intervention)
    t["payload"]["plan"]["affective_state"] = affect
    return t


class TestAffectMeasures:
    def test_no_negative_affect_nulls(self):
        """No frustration/disengaged → negative_affect_count=0, support/recovery=None."""
        run0 = make_run(0, tvd=0.5)
        t1 = _affect_turn(1, "curious")
        t2 = _affect_turn(2, "flow")
        m = compute_attempt_measures("p_test", "bell", [run0, t1, t2], BELL, SIM)
        assert m["negative_affect_count"] == 0
        assert m["negative_affect_rate"] == pytest.approx(0.0)
        assert m["affect_support_rate"] is None
        assert m["affect_recovery_rate"] is None

    def test_negative_affect_rate(self):
        """2 of 3 turns are frustration → rate=2/3."""
        run0 = make_run(0, tvd=0.5)
        t1 = _affect_turn(1, "frustration")
        t2 = _affect_turn(2, "curious")
        t3 = _affect_turn(3, "disengaged")
        m = compute_attempt_measures("p_test", "bell", [run0, t1, t2, t3], BELL, SIM)
        assert m["negative_affect_count"] == 2
        assert m["negative_affect_rate"] == pytest.approx(2 / 3)

    def test_affect_support_rate_full(self):
        """All negative-affect turns receive encourage → support_rate=1.0."""
        run0 = make_run(0, tvd=0.5)
        t1 = _affect_turn(1, "frustration", intervention="encourage")
        t2 = _affect_turn(2, "disengaged", intervention="encourage")
        m = compute_attempt_measures("p_test", "bell", [run0, t1, t2], BELL, SIM)
        assert m["affect_support_count"] == 2
        assert m["affect_support_rate"] == pytest.approx(1.0)

    def test_affect_support_rate_partial(self):
        """Only 1 of 2 negative-affect turns gets encourage → support_rate=0.5."""
        run0 = make_run(0, tvd=0.5)
        t1 = _affect_turn(1, "frustration", intervention="encourage")
        t2 = _affect_turn(2, "frustration", intervention="co_reason")  # not encourage
        m = compute_attempt_measures("p_test", "bell", [run0, t1, t2], BELL, SIM)
        assert m["affect_support_rate"] == pytest.approx(0.5)

    def test_affect_recovery_rate(self):
        """frustration → curious: the next plan_turn exits NEEDS_SUPPORT → rate=1.0."""
        run0 = make_run(0, tvd=0.5)
        t1 = _affect_turn(1, "frustration")
        t2 = _affect_turn(2, "curious")   # recovered
        m = compute_attempt_measures("p_test", "bell", [run0, t1, t2], BELL, SIM)
        assert m["affect_recovery_rate"] == pytest.approx(1.0)

    def test_affect_recovery_rate_none(self):
        """frustration → still frustration → rate=0.0."""
        run0 = make_run(0, tvd=0.5)
        t1 = _affect_turn(1, "frustration")
        t2 = _affect_turn(2, "disengaged")  # still NEEDS_SUPPORT
        m = compute_attempt_measures("p_test", "bell", [run0, t1, t2], BELL, SIM)
        assert m["affect_recovery_rate"] == pytest.approx(0.0)

    def test_control_turn_excluded(self):
        """Control turns (plan=None) are excluded from §5c denominators."""
        run0 = make_run(0, tvd=0.5)
        ctrl = {
            "participant_id": "p_test", "exercise_id": "bell",
            "event_type": "turn", "ts": _ts(1), "stance": "control",
            "payload": {"plan": None, "stance": "control",
                        "final_message": "Here if needed.", "telemetry": {}},
            "note": "",
        }
        t2 = _affect_turn(2, "frustration", intervention="encourage")
        m = compute_attempt_measures("p_test", "bell", [run0, ctrl, t2], BELL, SIM)
        # ctrl has plan=None so only t2 counts as a plan_turn
        assert m["negative_affect_count"] == 1
        assert m["affect_support_count"] == 1
        assert m["affect_support_rate"] == pytest.approx(1.0)

    def test_aggregate_affect_rates(self):
        """aggregate_participant averages §5c rates across rows."""
        row1 = {"participant_id": "pa", "stance": "peer", "n_turns": 2,
                "negative_affect_rate": 1.0, "affect_support_rate": 1.0,
                "affect_recovery_rate": 1.0, "n_escalated": 0}
        row2 = {"participant_id": "pa", "stance": "peer", "n_turns": 2,
                "negative_affect_rate": 0.5, "affect_support_rate": 0.0,
                "affect_recovery_rate": None, "n_escalated": 0}
        agg = aggregate_participant("pa", [row1, row2])
        assert agg["negative_affect_rate"] == pytest.approx(0.75)
        assert agg["affect_support_rate"] == pytest.approx(0.5)
        # _mean skips None, so only row1's 1.0 contributes
        assert agg["affect_recovery_rate"] == pytest.approx(1.0)


# ── §5e learner-model measures ────────────────────────────────────────────────

def _make_lm_turn(n, shaky_concepts=None, revisit_concept=None,
                  intervention="co_reason", stance="peer"):
    """make_turn variant with telemetry.learner_model populated."""
    t = make_turn(n, stance=stance, intervention=intervention)
    t["payload"]["telemetry"]["learner_model"] = {
        "due_review": shaky_concepts or [],
        "revisit_concept": revisit_concept,
        "n_shaky": len(shaky_concepts or []),
        "n_grasped": 0,
        "shaky_concepts": shaky_concepts or [],
    }
    if intervention == "revisit":
        t["payload"]["plan"]["intervention"] = "revisit"
    return t


class TestLearnerModelMeasures:
    def test_no_shaky_all_null(self):
        """No shaky concepts in trace → counts=0, rates=None."""
        run0 = make_run(0, tvd=0.5)
        t1 = _make_lm_turn(1, shaky_concepts=[])
        m = compute_learner_model_measures("p_test", [run0, t1], {})
        assert m["concepts_ever_shaky"] == 0
        assert m["shaky_resolution_rate"] is None
        assert m["revisit_resolution_rate"] is None
        assert m["nonrevisit_resolution_rate"] is None

    def test_shaky_resolved_rate(self):
        """One shaky concept that's grasped in end state → resolution rate=1.0."""
        run0 = make_run(0, tvd=0.5)
        t1 = _make_lm_turn(1, shaky_concepts=["entanglement"])
        end_concepts = {
            "entanglement": {"state": "grasped", "evidence": 2,
                             "last_seen": "ts", "last_review": None, "last_review_ex": None}
        }
        m = compute_learner_model_measures("p_test", [run0, t1], end_concepts)
        assert m["concepts_ever_shaky"] == 1
        assert m["concepts_grasped_end"] == 1
        assert m["shaky_resolution_rate"] == pytest.approx(1.0)

    def test_shaky_unresolved_rate_zero(self):
        """Shaky concept still shaky at end → resolution rate=0."""
        run0 = make_run(0, tvd=0.5)
        t1 = _make_lm_turn(1, shaky_concepts=["entanglement"])
        end_concepts = {
            "entanglement": {"state": "shaky", "evidence": 1,
                             "last_seen": "ts", "last_review": None, "last_review_ex": None}
        }
        m = compute_learner_model_measures("p_test", [run0, t1], end_concepts)
        assert m["shaky_resolution_rate"] == pytest.approx(0.0)

    def test_revisit_count_and_concept_tracked(self):
        """A revisit turn increments revisit_count and tracks the concept."""
        run0 = make_run(0, tvd=0.5)
        t1 = _make_lm_turn(1, shaky_concepts=["superposition"],
                            revisit_concept="superposition", intervention="revisit")
        m = compute_learner_model_measures("p_test", [run0, t1], {})
        assert m["revisit_count"] == 1
        assert m["distinct_concepts_revisited"] == 1

    def test_revisit_vs_nonrevisit_resolution_rates(self):
        """Two shaky concepts; one revisited+resolved, one not revisited+resolved.
        revisit_resolution_rate=1.0, nonrevisit_resolution_rate=1.0."""
        run0 = make_run(0, tvd=0.5)
        t1 = _make_lm_turn(1, shaky_concepts=["superposition", "entanglement"],
                            revisit_concept="superposition", intervention="revisit")
        end_concepts = {
            "superposition": {"state": "grasped", "evidence": 2,
                               "last_seen": "ts", "last_review": None, "last_review_ex": None},
            "entanglement": {"state": "grasped", "evidence": 2,
                              "last_seen": "ts", "last_review": None, "last_review_ex": None},
        }
        m = compute_learner_model_measures("p_test", [run0, t1], end_concepts)
        assert m["revisit_resolution_rate"] == pytest.approx(1.0)
        assert m["nonrevisit_resolution_rate"] == pytest.approx(1.0)

    def test_revisit_resolved_nonrevisit_not(self):
        """Revisited concept grasped; non-revisited still shaky.
        revisit_resolution_rate=1.0, nonrevisit_resolution_rate=0.0."""
        run0 = make_run(0, tvd=0.5)
        t1 = _make_lm_turn(1, shaky_concepts=["superposition", "entanglement"],
                            revisit_concept="superposition", intervention="revisit")
        end_concepts = {
            "superposition": {"state": "grasped", "evidence": 2,
                               "last_seen": "ts", "last_review": None, "last_review_ex": None},
            "entanglement": {"state": "shaky", "evidence": 1,
                              "last_seen": "ts", "last_review": None, "last_review_ex": None},
        }
        m = compute_learner_model_measures("p_test", [run0, t1], end_concepts)
        assert m["revisit_resolution_rate"] == pytest.approx(1.0)
        assert m["nonrevisit_resolution_rate"] == pytest.approx(0.0)
