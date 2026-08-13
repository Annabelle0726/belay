# SPDX-License-Identifier: AGPL-3.0-only
"""
Shared pytest fixtures for all tests.
"""

import pytest

from app.core.registry import get_active_pack


@pytest.fixture
def exercise_id():
    """Default exercise ID for testing."""
    return "ds-foundations"


@pytest.fixture
def exercise():
    """Get the default exercise."""
    pack = get_active_pack()
    return pack.get_exercise("ds-foundations")