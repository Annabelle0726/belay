# SPDX-License-Identifier: AGPL-3.0-only
"""Deployment-only ledger initialization, repeatable cleanup and recovery checks."""

import argparse

from ..config import settings
from ..store.db import engine
from .ledger import DeletionLedger
from .policy import Policy
from .repository import ConversationStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["init-ledger", "cleanup", "restore-check"])
    parser.add_argument("--backup-age-seconds", type=int)
    args = parser.parse_args()
    policy = Policy.from_settings(settings)
    policy.require()
    if args.action == "init-ledger":
        DeletionLedger(policy.deletion_ledger_file).initialize()
        print("dialogue deletion ledger initialized")
        return
    if args.action == "restore-check" and (
        args.backup_age_seconds is None
        or not 0 <= args.backup_age_seconds <= policy.backup_max_age_seconds
    ):
        parser.error("backup age must be supplied and within the approved maximum")
    count = ConversationStore(engine, policy).cleanup()
    print(f"dialogue cleanup complete: {count} attempts erased")


if __name__ == "__main__":
    main()
