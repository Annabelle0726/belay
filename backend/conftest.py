# SPDX-License-Identifier: AGPL-3.0-only
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))


import pytest


@pytest.fixture(autouse=True)
def _http_behavior_credentials(request, monkeypatch, tmp_path):
    # Existing governance/PII/widget HTTP tests now use real signed credentials.
    # Security tests own their config explicitly; this fixture never overrides authorize.
    if request.module.__name__.split(".")[-1] not in {
        "test_quad_sidecar",
        "test_goals",
        "test_overlay",
        "test_distress",
        "test_deploy",
    }:
        return
    from tests.http_auth import configure

    assignments = {"ds-foundations": "v1", "echo-1": "v1"}
    configure(
        monkeypatch,
        tmp_path,
        {
            "exercise_versions": assignments,
            "subjects": {
                pid: [
                    {
                        "institution_id": "test-institution",
                        "class_id": "test-class",
                        "learner_id": pid,
                        "assignments": assignments,
                    }
                ]
                for pid in ("gh:12345", "gh:7", "gh:9")
            },
        },
    )
