# SPDX-License-Identifier: AGPL-3.0-only
"""Run the actual operator CLI with temporary files and explicit process settings."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


def run_cli(tmp_path, *args, configured=True, overrides=None, module="maintenance"):
    env = {key: value for key, value in os.environ.items() if not key.startswith("DIALOGUE_")}
    env["DATABASE_URL"] = "sqlite:///" + str(tmp_path / "course.db")
    if configured:
        env.update(
            {
                "DIALOGUE_ENABLED": "0",
                "DIALOGUE_POLICY_ID": "local-test-only",
                "DIALOGUE_RETENTION_SECONDS": "3600",
                "DIALOGUE_BACKUP_MAX_AGE_SECONDS": "3600",
                "DIALOGUE_DELETION_LEDGER_FILE": str(tmp_path / "deletions.jsonl"),
            }
        )
    env.update(overrides or {})
    return subprocess.run(
        [sys.executable, "-m", "app.conversations." + module, *args],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_missing_policy_lists_env_names_without_traceback_or_file_creation(tmp_path):
    result = run_cli(tmp_path, "init-ledger", configured=False)
    assert result.returncode == 2
    for name in (
        "DIALOGUE_POLICY_ID",
        "DIALOGUE_RETENTION_SECONDS",
        "DIALOGUE_BACKUP_MAX_AGE_SECONDS",
        "DIALOGUE_DELETION_LEDGER_FILE",
    ):
        assert name in result.stderr
    assert ".env is not loaded automatically" in result.stderr
    assert "Traceback" not in result.stderr
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({"DIALOGUE_RETENTION_SECONDS": "one hour"}, "invalid numeric environment setting"),
        ({"DIALOGUE_PAGE_BYTES": "1"}, "6 * DIALOGUE_MAX_MESSAGE_BYTES + 1024"),
        ({"DIALOGUE_CONTEXT_TOKENS": "1024"}, "DIALOGUE_CONTEXT_TOKENS must be >"),
    ],
)
def test_invalid_policy_is_actionable_and_does_not_initialize(tmp_path, overrides, expected):
    result = run_cli(tmp_path, "init-ledger", overrides=overrides)
    assert result.returncode == 2 and expected in result.stderr
    assert "Traceback" not in result.stderr
    assert not (tmp_path / "deletions.jsonl").exists()


def test_init_works_with_web_saving_disabled_and_does_not_need_database(tmp_path):
    result = run_cli(tmp_path, "init-ledger", overrides={"DATABASE_URL": "invalid-unused-dsn"})
    assert result.returncode == 0, result.stderr
    ledger = tmp_path / "deletions.jsonl"
    assert ledger.read_text() == '{"schema":1}\n'
    content = ledger.read_text() + '{"conversation_id":"' + "a" * 32 + '"}\n'
    ledger.write_text(content)
    assert run_cli(tmp_path, "init-ledger").returncode == 0
    assert ledger.read_text() == content


def test_corrupt_ledger_is_never_reset_by_initialization(tmp_path):
    ledger = tmp_path / "deletions.jsonl"
    ledger.write_text("broken")
    result = run_cli(tmp_path, "init-ledger")
    assert result.returncode == 2 and "deletion ledger unavailable" in result.stderr
    assert "Traceback" not in result.stderr
    assert ledger.read_text() == "broken"


def test_cleanup_still_works_when_web_saving_is_disabled(tmp_path):
    assert run_cli(tmp_path, module="migration").returncode == 0
    assert run_cli(tmp_path, "init-ledger").returncode == 0
    result = run_cli(tmp_path, "cleanup")
    assert result.returncode == 0, result.stderr
    assert "0 attempts erased" in result.stdout
