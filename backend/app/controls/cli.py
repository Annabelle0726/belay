# SPDX-License-Identifier: AGPL-3.0-only
"""Run with python -m app.controls.cli; requires operator database credentials."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import create_engine

from .contracts import Amount, ControlError, Policy
from .ledger import Ledger
from .maintenance import reconcile, snapshot, unresolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "init",
            "update-policy",
            "summary",
            "unresolved",
            "settle-attempt",
            "confirm-stopped",
            "acknowledge-overrun",
        ],
    )
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--target")
    parser.add_argument(
        "--evidence", help="opaque incident reference (32-64 hexadecimal characters)"
    )
    parser.add_argument("--actual", type=Path, help="JSON Amount with authoritative usage")
    args = parser.parse_args(argv)
    url = os.environ.get("CONTROLS_DATABASE_URL")
    if not url:
        parser.error("CONTROLS_DATABASE_URL must name the operator-selected coordinator")
    engine = create_engine(url)
    ledger = Ledger(engine)
    output: dict
    try:
        if args.command in {"init", "update-policy"}:
            if not args.policy:
                parser.error("--policy is required")
            policy = Policy.model_validate_json(args.policy.read_text(encoding="utf-8"))
            (ledger.initialize if args.command == "init" else ledger.update_policy)(policy)
            output = {"policy_version": policy.version}
        elif args.command == "summary":
            output = snapshot(ledger)
        elif args.command == "unresolved":
            output = {"unresolved": unresolved(ledger)}
        else:
            if not args.target or not args.evidence:
                parser.error("--target and --evidence are required")
            actual = (
                Amount.model_validate_json(args.actual.read_text(encoding="utf-8"))
                if args.actual
                else None
            )
            reconcile(
                ledger,
                args.target,
                args.evidence,
                action=args.command.replace("-", "_"),
                actual=actual,
            )
            output = {"reconciled": args.target, "action": args.command}
        print(json.dumps(output, indent=2))
        return 0
    except (ControlError, ValueError, OSError) as exc:
        # Never print database connection strings, credentials or content.
        print(
            json.dumps(
                {"error": exc.code if isinstance(exc, ControlError) else "invalid_configuration"}
            )
        )
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
