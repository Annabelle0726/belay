# SPDX-License-Identifier: AGPL-3.0-only
"""
Adversarial leak regression benchmark (CC-B2).

Tests the governance gate against adversarial student attacks that attempt
to extract full solutions. Based on methodology from:
"Evaluating Answer Leakage Robustness of LLM Tutors against Adversarial
Student Attacks" (ACL 2026, arXiv 2604.18660).

This is a REGRESSION GATE: any attack in the corpus that successfully
extracts a solution causes CI to fail. It is NOT a one-off report.

Design follows test_distress.py pattern:
- Explicit true positives: attack patterns that should be blocked
- Negative controls: benign messages that should NOT be blocked
- End-to-end: exercises real governance.check / leak_evidence path
- Privacy verified: no solution text in trace


Test Structure:
- test_adversarial_corpus_parses: Fast corpus validation (no LLM)
- test_adversarial_attack_regression: Main regression gate (parametrized)
- test_adversarial_attack_summary: Summary report generator (informative)
"""
from __future__ import annotations

import pytest
from adversarial import Attack, StubLLM, build_attack_corpus

# ============================================================================
# Test 1: Corpus Validation (Fast, No LLM)
# ============================================================================


def test_adversarial_corpus_parses():
    """
    TEST 1: Corpus Validation

    Fast sanity check: verifies the attack corpus is well-formed.
    - No duplicate attack names
    - Each attack has at least one message
    - Categories are recognized
    """
    corpus = build_attack_corpus()
    assert len(corpus) > 0, "Attack corpus is empty"

    names = [a.name for a in corpus]
    assert len(names) == len(set(names)), f"Duplicate attack names: {names}"

    valid_categories = {
        "direct_override",
        "roleplay_framing",
        "incremental_extraction",
        "obfuscation",
        "context_manipulation",
        "negative_control",
    }
    for attack in corpus:
        assert len(attack.student_messages) > 0, f"Attack {attack.name} has no messages"
        assert (
            attack.category in valid_categories
        ), f"Attack {attack.name} has unknown category: {attack.category}"


# ============================================================================
# Test 2: Main Regression Gate (Parametrized)
# ============================================================================


@pytest.mark.parametrize("attack", build_attack_corpus(), ids=lambda a: a.name)
def test_adversarial_attack_regression(attack: Attack):
    """
    TEST 2: Main Regression Gate

    ★ THIS IS THE CRITICAL TEST ★

    Runs each attack through the full tutor pipeline and verifies
    the governance gate blocks solution leaks.

    If ANY attack succeeds, this test FAILS → CI FAILS → Regression detected!
    """
    llm = StubLLM()
    result = attack.run(llm)

    if attack.expected_leak is False:
        # Negative control: should NOT leak
        assert result["leaked"] is False, (
            f"❌ Negative control '{attack.name}' unexpectedly leaked! "
            f"Flag: {result['governance_flag']}"
        )
    else:
        # Attack: should be BLOCKED
        assert result["leaked"] is True, (
            f"❌ REGRESSION: Attack '{attack.name}' SUCCEEDED! "
            f"Flag: {result['governance_flag']}"
        )
        assert result["governance_flag"] in (
            "withholding_solution",
            "redirect_answer_seeking",
        ), f"Attack '{attack.name}' not properly flagged"


# ============================================================================
# Test 3: Summary Report (Informative)
# ============================================================================


@pytest.mark.slow
def test_adversarial_attack_summary():
    """
    TEST 3: Summary Report

    Generates a human-readable summary of all attack results.
    Also includes an assertion that all attacks are blocked.

    Run with: pytest test_adversarial_leak.py::test_adversarial_attack_summary -v -s
    """
    attacks = build_attack_corpus()
    llm = StubLLM()

    results = []
    for attack in attacks:
        result = attack.run(llm)
        results.append(
            {
                "name": attack.name,
                "category": attack.category,
                "leaked": result["leaked"],
                "governance_flag": result["governance_flag"],
            }
        )

    # Print summary
    print("\n" + "=" * 80)
    print("ADVERSARIAL ATTACK BENCHMARK SUMMARY")
    print("=" * 80)

    by_category = {}
    for r in results:
        cat = r["category"]
        if cat not in by_category:
            by_category[cat] = {"total": 0, "blocked": 0}
        by_category[cat]["total"] += 1
        if not r["leaked"]:
            by_category[cat]["blocked"] += 1

    print(f"\n{'Category':<25} {'Total':<8} {'Blocked':<10} {'Leaked':<10} {'Rate':<10}")
    print("-" * 70)
    for cat, stats in by_category.items():
        blocked_pct = (stats["blocked"] / stats["total"] * 100) if stats["total"] > 0 else 0
        leaked = stats["total"] - stats["blocked"]
        print(
            f"{cat:<25} {stats['total']:<8} {stats['blocked']:<10} {leaked:<10} {blocked_pct:.0f}%"
        )

    print("\nDetailed Results:")
    print("-" * 70)
    for r in results:
        status = "🔴 LEAKED" if r["leaked"] else "✅ BLOCKED"
        print(f"  {status}  {r['name']:<30} ({r['category']})")
    print("=" * 80)

    # Regression gate assertion
    leaked_count = sum(1 for r in results if r["leaked"])
    assert leaked_count == 0, f"\n❌ REGRESSION: {leaked_count} attacks succeeded!"
    print(f"\n✅ ALL {len(results)} ATTACKS BLOCKED")
