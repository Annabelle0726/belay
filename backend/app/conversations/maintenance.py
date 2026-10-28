# SPDX-License-Identifier: AGPL-3.0-only
"""Deployment-only ledger initialization, repeatable cleanup and recovery checks."""

import argparse
from dataclasses import replace

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from .ledger import DeletionLedger
from .policy import Policy


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["init-ledger", "cleanup", "restore-check"])
    parser.add_argument("--backup-age-seconds", type=int)
    args = parser.parse_args(argv)
    # Explicit administrative cleanup remains possible while web saving is OFF.
    try:
        from ..config import settings

        policy = replace(Policy.from_settings(settings), enabled=True)
    except ValueError:
        parser.error(
            "invalid numeric environment setting; dialogue durations and limits use integers"
        )
    errors = policy.configuration_errors()
    if errors:
        parser.error(
            "\n"
            + "\n".join(errors)
            + "\nSet these variables in this process; .env is not loaded automatically. See docs/conversations.md."
        )
    if args.action == "restore-check" and (
        args.backup_age_seconds is None
        or not 0 <= args.backup_age_seconds <= policy.backup_max_age_seconds
    ):
        parser.error("backup age must be supplied and within the approved maximum")
    try:
        if args.action == "init-ledger":
            DeletionLedger(policy.deletion_ledger_file).initialize()
            print("dialogue deletion ledger initialized")
            return
        # Ledger initialization does not need a database connection/configuration.
        from ..store.db import engine
        from .repository import ConversationStore

        count = ConversationStore(engine, policy).cleanup()
        print(f"dialogue cleanup complete: {count} attempts erased")
    except HTTPException as error:
        parser.error(str(error.detail))
    except OSError:
        parser.error(
            "cannot initialize deletion ledger; check its parent directory and permissions"
        )
    except SQLAlchemyError:
        parser.error("dialogue database operation failed; check DATABASE_URL and run the migration")


if __name__ == "__main__":
    main()
