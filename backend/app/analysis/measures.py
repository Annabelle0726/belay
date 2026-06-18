# SPDX-License-Identifier: AGPL-3.0-only
"""
§6 Process-measure extraction (pure, offline, no model/network).

Implements every definition in process_measures.md v5 (§2–§5e).
Identical input trace ⇒ identical output, byte-for-byte.

Key path conventions in the on-disk JSONL (make_event + export_jsonl):

  run event  payload keys:
    payload["source"]               — functional-model text
    payload["result"]["goalMet"]    — bool
    payload["result"]["tvd"]        — float (spec calls this "result.distance")
    payload["result"]["ok"]         — bool

  turn event payload keys:
    payload["plan"]["intervention"]      payload["plan"]["confidence"]
    payload["plan"]["affective_state"]
    payload["self_eval"]["confidence"]   payload["self_eval"]["leak_risk"]
    payload["self_eval"]["needs_revision"]
    payload["governance"]["flag"]        payload["governance"]["block"]
    payload["telemetry"]["escalated"]    payload["telemetry"]["abstained"]
    payload["telemetry"]["reasoning_effort"]
    payload["telemetry"]["confidence_trajectory"]
    payload["telemetry"]["worked_example"]
    payload["telemetry"]["learner_model"]   — {due_review, revisit_concept,
                                               n_shaky, n_grasped, shaky_concepts}
    payload["final_message"]
    payload["stance"]   (also event["stance"] at top level)

§5e learner-model measures additionally require the end learner_state.concepts
snapshot (passed as end_concepts to compute_learner_model_measures).

Note: control turns have plan/self_eval/governance = None in the payload.
All accessors use ``(x or {})`` to guard against None.
"""

from __future__ import annotations

from ..core.domain import DomainPack
from ..core.registry import get_active_pack

# ── constants -----------------------------------------------------------------
GOAL_TOL = 0.07  # matches every exercise's tol
HANDOFF_WINDOW = 2  # §1 "next 2 run events"
ECE_BINS = 10  # §4b


# ── §1 progress primitives ---------------------------------------------------


def _metric(run_event: dict) -> float:
    """Pack-agnostic primary scalar from a run event (§6 ``result.metric``).

    Reads the generic top-level ``metric`` slot, falling back to the legacy
    ``tvd`` (top level, then inside ``result.pack``) so pre-v6 traces still parse.

    Errors / missing metric return 1.0 rather than float("inf"): inf causes
    0 * inf = nan in the linear-slope sum when the first run fails, poisoning
    metric_slope and all downstream aggregates. The metric is used as a
    lower-is-better progress proxy alongside the authoritative goalMet signal.
    """
    res = (run_event.get("payload") or {}).get("result") or {}
    if not res.get("ok"):
        return 1.0
    val = res.get("metric")
    if val is None:
        val = res.get("tvd")
    if val is None:
        val = (res.get("pack") or {}).get("tvd")
    return float(val) if val is not None else 1.0


def _goal_met(run_event: dict) -> bool:
    res = (run_event.get("payload") or {}).get("result") or {}
    return bool(res.get("ok") and res.get("goalMet"))


def _source(run_event: dict) -> str:
    return (run_event.get("payload") or {}).get("source") or ""


def _linear_slope(values: list[float]) -> float | None:
    """Slope of a simple OLS fit of values vs index.  Returns None for <2 points."""
    n = len(values)
    if n < 2:
        return None
    xs = list(range(n))
    sx = sum(xs)
    sy = sum(values)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, values, strict=False))
    denom = n * sxx - sx * sx
    if denom == 0:
        return 0.0
    return (n * sxy - sx * sy) / denom


# ── op-level revision (§5) ---------------------------------------------------


def nontrivial_revision(src_a: str, src_b: str, pack=None) -> bool:
    """True iff the two submissions are structurally different programs.

    Pack-agnostic: delegates to ``pack.program_signature`` — a parse-only
    structural fingerprint (no execution) that ignores whitespace/comments. Two
    sources differing only in formatting compare equal; meaningfully different
    programs compare unequal.
    """
    pack = pack or get_active_pack()
    return pack.program_signature(src_a) != pack.program_signature(src_b)  # type: ignore[no-any-return]  # opaque parse-only fingerprint (Any); != is bool at runtime


# ── per-turn field accessors --------------------------------------------------


def _tp(turn_event: dict) -> dict:
    """Safe flattened view of a turn payload; guards against None sub-dicts."""
    p = turn_event.get("payload") or {}
    plan = p.get("plan") or {}
    se = p.get("self_eval") or {}
    gov = p.get("governance") or {}
    tel = p.get("telemetry") or {}
    return {
        "intervention": plan.get("intervention", "observe"),
        "plan_confidence": plan.get("confidence"),
        "se_confidence": se.get("confidence"),
        "se_leak_risk": se.get("leak_risk", "none"),
        "se_needs_revision": se.get("needs_revision", False),
        "gov_flag": gov.get("flag", "none"),
        "gov_block": gov.get("block", False),
        "escalated": tel.get("escalated", False),
        "abstained": tel.get("abstained", False),
        "reasoning_effort": tel.get("reasoning_effort"),
        "confidence_trajectory": tel.get("confidence_trajectory") or {},
        "final_message": p.get("final_message") or "",
        "stance": p.get("stance") or turn_event.get("stance"),
        # §5d worked-example verification (None for non-worked_analogy turns)
        "we_tel": tel.get("worked_example"),
        # §5c affect-response: affective_state from the Planner (None for control turns)
        "affect": plan.get("affective_state"),
    }


# ── §2 hand-offs --------------------------------------------------------------


def realized_handoff(
    turn_event: dict, target=None, tol=None, sim=None, pack: DomainPack | None = None, exercise=None
) -> bool:
    """True iff the code in final_message independently meets the exercise goal.

    Delegates to the active pack's `leak_evidence` — the identical executable
    oracle governance.check() uses — so realized_handoff and withholding_solution
    can never disagree on whether a snippet solves the exercise. Pass the full
    ``exercise`` (the pack may need its id to load a spec); the legacy
    ``target``/``tol`` form is kept for legacy callers. (``sim`` is accepted for
    backward compatibility; the pack's grader is deterministic.)
    """
    pack = pack or get_active_pack()
    fm = _tp(turn_event)["final_message"]
    ex = exercise if exercise is not None else {"target": target, "tol": tol}
    return pack.leak_evidence(fm, ex).is_solution  # type: ignore[arg-type]  # ex is the exercise dict / {target,tol} fallback; Exercise is a structural TypedDict


def attempted_handoff(turn_event: dict) -> bool:
    return _tp(turn_event)["gov_flag"] == "withholding_solution"  # type: ignore[no-any-return]  # comparison over the untyped §6 trace dict; bool at runtime


# ── §3 redirects --------------------------------------------------------------


def redirect(turn_event: dict) -> bool:
    return _tp(turn_event)["gov_flag"] == "redirect_answer_seeking"  # type: ignore[no-any-return]  # untyped §6 trace dict; bool at runtime


# ── §4a leak calibration ------------------------------------------------------


def predicted_leak(turn_event: dict) -> bool:
    """Primary: leak_risk in {partial, full}."""
    return _tp(turn_event)["se_leak_risk"] in {"partial", "full"}


def predicted_leak_strict(turn_event: dict) -> bool:
    """Strict variant: leak_risk == 'full' only."""
    return _tp(turn_event)["se_leak_risk"] == "full"  # type: ignore[no-any-return]  # untyped §6 trace dict; bool at runtime


def actual_leak(turn_event: dict) -> bool:
    return _tp(turn_event)["gov_flag"] == "withholding_solution"  # type: ignore[no-any-return]  # comparison over the untyped §6 trace dict; bool at runtime


# ── §5 repeated-error count ---------------------------------------------------


def _fail_sig(run_event: dict):
    """Fingerprint of a failing run; None means goal met (not a failure).

    Pack-agnostic: keys off the generic ``ok`` / ``goalMet`` / ``metric`` fields,
    so two consecutive failing runs at the same primary metric read as a repeated
    error in any pack (e.g. the DS held-out score / loss). No domain-specific
    distribution shape is read.
    """
    res = (run_event.get("payload") or {}).get("result") or {}
    if not res.get("ok"):
        return ("compile_error", (res.get("error") or "")[:80])
    if res.get("goalMet"):
        return None  # success — resets the streak
    return ("runtime", round(_metric(run_event), 4))


def _repeated_error_count(run_events: list) -> int:
    """Number of consecutive run-pairs sharing the same failing signature."""
    count = 0
    prev: object = object()  # sentinel: never equal to a real sig
    for run in run_events:
        sig = _fail_sig(run)
        if sig is not None and sig == prev:
            count += 1
        prev = sig  # goal_met gives sig=None, which resets prev
    return count


# ── §4b outcome computation ---------------------------------------------------


def _outcome_for_turn(
    turn_event: dict, run_events: list, window: int = HANDOFF_WINDOW
) -> bool | None:
    """True/False outcome for a guiding turn; None if no subsequent run exists.

    outcome = any run within the next `window` runs (after this turn's ts)
              satisfies progress_run OR goal_met.
    """
    ts = turn_event["ts"]
    subsequent = sorted(
        [r for r in run_events if r["ts"] > ts],
        key=lambda r: r["ts"],
    )[:window]
    if not subsequent:
        return None  # excluded from §4b per §7
    prior_best = min(
        (_metric(r) for r in run_events if r["ts"] <= ts),
        default=float("inf"),
    )
    current_best = prior_best
    for run in subsequent:
        tvd = _metric(run)
        if _goal_met(run) or tvd < current_best:
            return True
        current_best = min(current_best, tvd)
    return False


# ── §4b/4c calibration stats -------------------------------------------------


def ece(pairs: list[tuple[float, int]], n_bins: int = ECE_BINS) -> float:
    """Expected Calibration Error (equal-width bins)."""
    if not pairs:
        return 0.0
    bins: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for conf, out in pairs:
        b = min(int(conf * n_bins), n_bins - 1)
        bins[b].append((conf, out))
    total = len(pairs)
    err = 0.0
    for b_pairs in bins:
        if b_pairs:
            conf_avg = sum(c for c, _ in b_pairs) / len(b_pairs)
            acc = sum(o for _, o in b_pairs) / len(b_pairs)
            err += len(b_pairs) * abs(conf_avg - acc)
    return err / total


def brier_score(pairs: list[tuple[float, int]]) -> float:
    """Mean squared error of confidence vs binary outcome."""
    if not pairs:
        return 0.0
    return sum((c - o) ** 2 for c, o in pairs) / len(pairs)


# ── §5 struggle span classification ------------------------------------------


def _span_class(run_events: list, tvd_slope: float | None, repeated_error_count: int) -> str:
    """productive / unproductive_stuck / neutral (per §5)."""
    n = len(run_events)
    has_progress = any(
        _metric(r) < min((_metric(p) for p in run_events[:i]), default=float("inf"))
        for i, r in enumerate(run_events)
        if i > 0
    )
    if n >= 2 and tvd_slope is not None and tvd_slope < 0 and has_progress:
        return "productive"
    if n >= 3 and not has_progress and repeated_error_count > 0:
        return "unproductive_stuck"
    return "neutral"


# ── §5 engaged span without handoff ------------------------------------------


def _engaged_span(all_events: list, rh_set: set) -> int:
    """Longest run of consecutive events (turn + run) with no realized handoff.

    rh_set: set of id(turn_event) for turns where realized_handoff is True.
    A realized-handoff turn RESETS the span counter.
    """
    max_span = 0
    cur = 0
    for ev in all_events:
        if ev["event_type"] == "turn" and id(ev) in rh_set:
            max_span = max(max_span, cur)
            cur = 0
        else:
            cur += 1
    return max(max_span, cur)


# ── §4c abstention calibration ------------------------------------------------


def _abstention_calibration(turns: list, run_events: list, window: int = HANDOFF_WINDOW) -> dict:
    """Abstention precision and false abstention rate (§4c)."""
    abstained_turns = [t for t in turns if _tp(t)["abstained"]]
    if not abstained_turns:
        return {"abstention_precision": None, "false_abstention_rate": None, "n_abstained": 0}
    correct = 0  # no progress in window (abstention was warranted)
    false_a = 0  # student did/would progress
    for t in abstained_turns:
        outcome = _outcome_for_turn(t, run_events, window)
        if outcome is True:
            false_a += 1
        else:
            correct += 1  # None (no window) counts as "could not progress" here
    total = len(abstained_turns)
    return {
        "abstention_precision": correct / total,
        "false_abstention_rate": false_a / total,
        "n_abstained": total,
    }


# ── top-level per-(participant × exercise) computation -----------------------


def compute_attempt_measures(
    pid: str,
    exercise_id: str,
    events: list,
    exercise_meta: dict,
    sim=None,
    handoff_window: int = HANDOFF_WINDOW,
) -> dict:
    """All §2–§5b measures for one (participant_id × exercise_id) slice.

    `events` must be pre-sorted by ts (ascending).
    `exercise_meta` is the exercise dict; packs that grade by spec (DS) need only
    its id, so ``target``/``tol`` are optional (legacy execution-graded packs use them).
    """
    target = exercise_meta.get("target", {})
    tol = exercise_meta.get("tol", GOAL_TOL)

    runs = [e for e in events if e["event_type"] == "run"]
    turns = [e for e in events if e["event_type"] == "turn"]
    n_turns = len(turns)
    n_runs = len(runs)

    # ── §1 progress primitives ───────────────────────────────────────────────
    run_tvds = [_metric(r) for r in runs]
    run_goals = [_goal_met(r) for r in runs]

    best_so_far: list[float] = []
    cur_best = float("inf")
    for tvd in run_tvds:
        cur_best = min(cur_best, tvd)
        best_so_far.append(cur_best)

    solved_indices = [i for i, gm in enumerate(run_goals) if gm]
    solved = len(solved_indices) > 0
    solved_at_idx = solved_indices[0] if solved else None

    # "run events before solved_at" (§5)
    attempts_to_solve = solved_at_idx if solved else n_runs

    if solved:
        solve_ts = runs[solved_at_idx]["ts"]  # type: ignore[index]  # guarded by `if solved`: solved_at_idx is an int here
        turns_to_solve = sum(1 for t in turns if t["ts"] < solve_ts)
    else:
        turns_to_solve = n_turns

    tvd_slope = _linear_slope(best_so_far)

    # ── §2 hand-offs ─────────────────────────────────────────────────────────
    rh_set: set = set()  # id(turn) for realized handoff turns
    realized_hc = 0
    attempted_hc = 0
    for turn in turns:
        rh = realized_handoff(turn, target, tol, sim, exercise=exercise_meta)
        if rh:
            rh_set.add(id(turn))
            realized_hc += 1
        if attempted_handoff(turn):
            attempted_hc += 1

    realized_handoff_rate = realized_hc / n_turns if n_turns else 0.0
    attempted_handoff_rate = attempted_hc / n_turns if n_turns else 0.0

    # ── §3 redirects ─────────────────────────────────────────────────────────
    redirect_c = sum(redirect(t) for t in turns)
    redirect_rate = redirect_c / n_turns if n_turns else 0.0

    # ── §4a leak calibration (2×2) ───────────────────────────────────────────
    lp_list = [predicted_leak(t) for t in turns]
    lp_strict_list = [predicted_leak_strict(t) for t in turns]
    la_list = [actual_leak(t) for t in turns]
    leak_tp = sum(p and a for p, a in zip(lp_list, la_list, strict=False))
    leak_fp = sum(p and not a for p, a in zip(lp_list, la_list, strict=False))
    leak_fn = sum(not p and a for p, a in zip(lp_list, la_list, strict=False))
    leak_tn = sum(not p and not a for p, a in zip(lp_list, la_list, strict=False))
    n_actual_leak = leak_tp + leak_fn
    leak_miss_rate = leak_fn / n_actual_leak if n_actual_leak else None
    n_predicted_leak = sum(lp_list)
    n_predicted_leak_strict = sum(lp_strict_list)

    # ── §4c abstention ───────────────────────────────────────────────────────
    ab = _abstention_calibration(turns, runs, handoff_window)

    # ── §5 struggle markers ──────────────────────────────────────────────────
    re_count = _repeated_error_count(runs)
    span_cls = _span_class(runs, tvd_slope, re_count)

    sources = [_source(r) for r in runs]
    nr_count = sum(
        1 for a, b in zip(sources, sources[1:], strict=False) if nontrivial_revision(a, b)
    )

    self_directed = n_runs / (n_runs + n_turns) if (n_runs + n_turns) > 0 else 0.0

    engaged_span = _engaged_span(events, rh_set)

    # ── §5b escalation rate ──────────────────────────────────────────────────
    n_escalated = sum(
        1
        for t in turns
        if (t.get("payload") or {}).get("telemetry") is not None
        and ((t.get("payload") or {}).get("telemetry") or {}).get("escalated", False)
    )
    escalation_rate = n_escalated / n_turns if n_turns else 0.0

    # ── §5d worked-example verification ──────────────────────────────────────
    # Only worked_analogy turns that produced an example have we_tel != None.
    # Control turns and all other interventions carry None and are excluded.
    we_tps = [_tp(t)["we_tel"] for t in turns if _tp(t)["we_tel"] is not None]
    we_count = len(we_tps)
    we_verified_count = sum(1 for w in we_tps if w.get("verified"))
    we_verified_rate = we_verified_count / we_count if we_count else None
    we_retries_list = [w.get("retries", 0) for w in we_tps]
    we_retry_rate = sum(we_retries_list) / len(we_retries_list) if we_retries_list else None

    # ── §5c affect-response measures ─────────────────────────────────────────
    # plan_turns = turns that have a non-null plan (control turns excluded).
    # All three measures are None when negative_affect_count == 0 (null-not-0 rule).
    _NEEDS_SUPPORT = {"frustration", "disengaged"}
    plan_tps = [_tp(t) for t in turns if (t.get("payload") or {}).get("plan") is not None]
    negative_affect_count = sum(1 for tp in plan_tps if tp["affect"] in _NEEDS_SUPPORT)
    negative_affect_rate = negative_affect_count / n_turns if n_turns else 0.0
    affect_support_count = sum(
        1 for tp in plan_tps if tp["affect"] in _NEEDS_SUPPORT and tp["intervention"] == "encourage"
    )
    affect_support_rate = (
        affect_support_count / negative_affect_count if negative_affect_count else None
    )
    # Recovery: among neg-affect plan_turns with a subsequent plan_turn, how often
    # does the next plan_turn's affect exit NEEDS_SUPPORT?
    recovered_count = with_next_count = 0
    for i, tp in enumerate(plan_tps):
        if tp["affect"] not in _NEEDS_SUPPORT:
            continue
        if i + 1 < len(plan_tps):
            with_next_count += 1
            if plan_tps[i + 1]["affect"] not in _NEEDS_SUPPORT:
                recovered_count += 1
    affect_recovery_rate = recovered_count / with_next_count if with_next_count else None

    # stance from the first turn event (all turns in a session have same stance)
    stance_val = None
    for t in turns:
        s = (t.get("payload") or {}).get("stance") or t.get("stance")
        if s:
            stance_val = s
            break

    return {
        "participant_id": pid,
        "exercise_id": exercise_id,
        "stance": stance_val,
        "cohort": None,
        # §2
        "realized_handoff_count": realized_hc,
        "attempted_handoff_count": attempted_hc,
        "realized_handoff_rate": realized_handoff_rate,
        "attempted_handoff_rate": attempted_handoff_rate,
        # §3
        "redirect_count": redirect_c,
        "redirect_rate": redirect_rate,
        # §4a
        "n_turns": n_turns,
        "n_predicted_leak": n_predicted_leak,
        "n_predicted_leak_strict": n_predicted_leak_strict,
        "n_actual_leak": n_actual_leak,
        "leak_tp": leak_tp,
        "leak_fp": leak_fp,
        "leak_fn": leak_fn,
        "leak_tn": leak_tn,
        "leak_miss_rate": leak_miss_rate,
        # §4c
        "n_abstained": ab["n_abstained"],
        "abstention_precision": ab["abstention_precision"],
        "false_abstention_rate": ab["false_abstention_rate"],
        # §5
        "solved": solved,
        "attempts_to_solve": attempts_to_solve,
        "turns_to_solve": turns_to_solve,
        "tvd_slope": tvd_slope,
        "repeated_error_count": re_count,
        "engaged_span_without_handoff": engaged_span,
        "nontrivial_revision_count": nr_count,
        "self_directed_ratio": self_directed,
        "span_class": span_cls,
        # §5b
        "n_escalated": n_escalated,
        "escalation_rate": escalation_rate,
        # §5d worked-example verification
        "worked_example_count": we_count,
        "worked_example_verified_rate": we_verified_rate,
        "worked_example_retry_rate": we_retry_rate,
        # §5c affect-response
        "negative_affect_count": negative_affect_count,
        "negative_affect_rate": negative_affect_rate,
        "affect_support_count": affect_support_count,
        "affect_support_rate": affect_support_rate,
        "affect_recovery_rate": affect_recovery_rate,
    }


def compute_calibration_pairs(
    pid: str,
    exercise_id: str,
    events: list,
    exercise_meta: dict,
    sim=None,
    window: int = HANDOFF_WINDOW,
) -> list[dict]:
    """One row per turn combining §4a, §4b, §4c raw signals.

    Rows for non-guiding turns (observe) have outcome=None and are excluded
    from §4b ECE/Brier but retained for §4a (leak self-detection).
    """
    turns = [e for e in events if e["event_type"] == "turn"]
    runs = [e for e in events if e["event_type"] == "run"]

    rows = []
    for i, turn in enumerate(turns):
        tp = _tp(turn)
        is_guiding = tp["intervention"] != "observe"
        outcome = _outcome_for_turn(turn, runs, window) if is_guiding else None
        rows.append(
            {
                "participant_id": pid,
                "exercise_id": exercise_id,
                "turn_index": i,
                "confidence": tp["se_confidence"],
                "outcome": int(outcome) if outcome is not None else None,
                "leak_predicted": predicted_leak(turn),
                "leak_predicted_strict": predicted_leak_strict(turn),
                "leak_actual": actual_leak(turn),
                "abstained": tp["abstained"],
            }
        )
    return rows


def aggregate_participant(pid: str, attempt_rows: list[dict]) -> dict:
    """Aggregate all (pid, exercise) rows into a per-participant summary."""

    def _mean(vals):
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None

    def _rate(num_key, denom_key):
        total = sum(r.get(denom_key, 0) for r in attempt_rows)
        if not total:
            return None
        return sum(r.get(num_key, 0) for r in attempt_rows) / total

    stances = list({r.get("stance") for r in attempt_rows if r.get("stance")})
    stance = stances[0] if len(stances) == 1 else ("mixed" if stances else None)

    tp = sum(r.get("leak_tp", 0) for r in attempt_rows)
    fp = sum(r.get("leak_fp", 0) for r in attempt_rows)
    fn = sum(r.get("leak_fn", 0) for r in attempt_rows)
    tn = sum(r.get("leak_tn", 0) for r in attempt_rows)
    al = tp + fn
    pl = tp + fp
    leak_precision = tp / pl if pl else None
    leak_recall = tp / al if al else None
    leak_miss_rate = fn / al if al else None

    total_turns = sum(r.get("n_turns", 0) for r in attempt_rows)
    total_esc = sum(r.get("n_escalated", 0) for r in attempt_rows)

    peer_turns = sum(r.get("n_turns", 0) for r in attempt_rows if r.get("stance") == "peer")
    oracle_turns = sum(r.get("n_turns", 0) for r in attempt_rows if r.get("stance") == "oracle")
    peer_esc = sum(r.get("n_escalated", 0) for r in attempt_rows if r.get("stance") == "peer")
    oracle_esc = sum(r.get("n_escalated", 0) for r in attempt_rows if r.get("stance") == "oracle")

    return {
        "participant_id": pid,
        "stance": stance,
        "cohort": (attempt_rows[0].get("cohort") if attempt_rows else None),
        "n_exercises": len(attempt_rows),
        "pct_solved": _mean([1.0 if r.get("solved") else 0.0 for r in attempt_rows]),
        "avg_attempts_to_solve": _mean([r.get("attempts_to_solve") for r in attempt_rows]),
        "avg_turns_to_solve": _mean([r.get("turns_to_solve") for r in attempt_rows]),
        "realized_handoff_rate": _rate("realized_handoff_count", "n_turns"),
        "attempted_handoff_rate": _rate("attempted_handoff_count", "n_turns"),
        "redirect_rate": _rate("redirect_count", "n_turns"),
        # §4a 2×2
        "leak_tp": tp,
        "leak_fp": fp,
        "leak_fn": fn,
        "leak_tn": tn,
        "leak_precision": leak_precision,
        "leak_recall": leak_recall,
        "leak_miss_rate": leak_miss_rate,
        # §4c
        "n_abstained": sum(r.get("n_abstained", 0) for r in attempt_rows),
        "abstention_precision": _mean([r.get("abstention_precision") for r in attempt_rows]),
        "false_abstention_rate": _mean([r.get("false_abstention_rate") for r in attempt_rows]),
        # §5
        "avg_tvd_slope": _mean([r.get("tvd_slope") for r in attempt_rows]),
        "avg_nontrivial_revisions": _mean(
            [r.get("nontrivial_revision_count") for r in attempt_rows]
        ),
        "avg_engaged_span": _mean([r.get("engaged_span_without_handoff") for r in attempt_rows]),
        # §5b escalation
        "escalation_rate": total_esc / total_turns if total_turns else None,
        "escalation_rate_peer": peer_esc / peer_turns if peer_turns else None,
        "escalation_rate_oracle": oracle_esc / oracle_turns if oracle_turns else None,
        # §5d worked-example verification
        "worked_example_count": sum(r.get("worked_example_count", 0) for r in attempt_rows),
        "worked_example_verified_rate": _mean(
            [r.get("worked_example_verified_rate") for r in attempt_rows]
        ),
        "worked_example_retry_rate": _mean(
            [r.get("worked_example_retry_rate") for r in attempt_rows]
        ),
        # §5c affect-response
        "negative_affect_rate": _mean([r.get("negative_affect_rate") for r in attempt_rows]),
        "affect_support_rate": _mean([r.get("affect_support_rate") for r in attempt_rows]),
        "affect_recovery_rate": _mean([r.get("affect_recovery_rate") for r in attempt_rows]),
    }


# ── §5e longitudinal learner-model measures ──────────────────────────────────


def compute_learner_model_measures(
    pid: str,
    all_events: list,
    end_concepts: dict,
) -> dict:
    """§5e participant-level measures, cross-exercise.

    `all_events` — the full ordered trace (run + turn events) for this participant.
    `end_concepts` — the end-state LearnerState.concepts snapshot:
                     {concept_id: {"state":"shaky"|"grasped", "evidence":int, ...}}

    All rates are None when the denominator is zero (null-not-0 rule).
    """
    turns = [e for e in all_events if e["event_type"] == "turn"]

    # Collect concept_ids ever seen as shaky (from per-turn learner_model telemetry).
    ever_shaky_set: set = set()
    revisited_concepts: set = set()
    revisit_count = 0

    for turn in turns:
        tel = (turn.get("payload") or {}).get("telemetry") or {}
        lm = tel.get("learner_model") or {}
        for cid in lm.get("shaky_concepts") or []:
            ever_shaky_set.add(cid)
        rc = lm.get("revisit_concept")
        if rc:
            revisited_concepts.add(rc)
        tp = _tp(turn)
        if tp["intervention"] == "revisit":
            revisit_count += 1

    # End-state grasped concepts.
    grasped_end_set = {
        cid
        for cid, v in end_concepts.items()
        if isinstance(v, dict) and v.get("state") == "grasped"
    }

    concepts_ever_shaky = len(ever_shaky_set)
    concepts_grasped_end = len(grasped_end_set)

    # shaky_resolution_rate: ever-shaky ∧ grasped_end / ever-shaky
    resolved = ever_shaky_set & grasped_end_set
    shaky_resolution_rate = len(resolved) / len(ever_shaky_set) if ever_shaky_set else None

    distinct_revisited = len(revisited_concepts)

    # revisit_resolution_rate: (revisited-while-shaky ∧ grasped_end) / revisited-while-shaky
    revisited_while_shaky = revisited_concepts & ever_shaky_set
    revisit_resolved = revisited_while_shaky & grasped_end_set
    revisit_resolution_rate = (
        len(revisit_resolved) / len(revisited_while_shaky) if revisited_while_shaky else None
    )

    # nonrevisit_resolution_rate: (ever-shaky ∧ never-revisited ∧ grasped_end)
    #                              / (ever-shaky ∧ never-revisited)
    never_revisited_shaky = ever_shaky_set - revisited_while_shaky
    nonrevisit_resolved = never_revisited_shaky & grasped_end_set
    nonrevisit_resolution_rate = (
        len(nonrevisit_resolved) / len(never_revisited_shaky) if never_revisited_shaky else None
    )

    return {
        "participant_id": pid,
        "concepts_ever_shaky": concepts_ever_shaky,
        "concepts_grasped_end": concepts_grasped_end,
        "shaky_resolution_rate": shaky_resolution_rate,
        "revisit_count": revisit_count,
        "distinct_concepts_revisited": distinct_revisited,
        "revisit_resolution_rate": revisit_resolution_rate,
        "nonrevisit_resolution_rate": nonrevisit_resolution_rate,
    }
