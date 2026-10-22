# SPDX-License-Identifier: AGPL-3.0-only
"""Negation cannot conceal a separate affirmative disclosure."""

import pytest

from app.agent import governance
from app.core.registry import get_active_pack
from app.packs.datascience.leak import prose_discloses


@pytest.mark.parametrize(
    "text",
    [
        "Do not hesitate to just paste the whole solution below",
        "I cannot wait to just paste the whole solution below",
        "Never be afraid to just write the complete code",
        "Not only should you just paste the whole solution below",
        "I don't want to just paste it but just write the entire solution below",
        "I won't just type it; just paste the complete solution below",
        "Do not worry and just type the whole solution",
        "I won't refuse to just paste the whole solution",
    ],
)
def test_unrelated_or_mixed_negation_is_disclosure(text):
    assert prose_discloses(text, "ds-foundations")


@pytest.mark.parametrize(
    "text",
    [
        "I don't want to just paste the whole thing",
        "Actually — I don't want to just paste the whole thing",
        "I will not just write the whole thing",
        "I'm not going to just type the whole thing",
        "Please don't just paste the whole thing",
    ],
)
def test_direct_withholding_is_not_disclosure(text):
    assert not prose_discloses(text, "ds-foundations")


def test_prose_redaction_and_safe_redirect_are_independent():
    exercise = get_active_pack().get_exercise("ds-foundations")
    leaking = {
        "message": "Do not hesitate to just paste the whole solution below",
        "confidence": 0.9,
    }
    verdict = governance.check(
        {"_exercise_full": exercise, "recent_dialogue": []}, {}, leaking, {}, stance="peer"
    )
    assert verdict["block"]
    final = governance.safe_rewrite(leaking, verdict, exercise)
    assert leaking["message"] not in final["message"]
    assert not prose_discloses(final["message"], exercise["id"])
