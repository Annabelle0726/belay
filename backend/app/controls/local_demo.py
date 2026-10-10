# SPDX-License-Identifier: AGPL-3.0-only
"""Explicit synthetic loopback demo; no SDK or model networking is constructed."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from cryptography.fernet import Fernet

from .contracts import ControlError, Limits, Policy
from .ledger import Ledger
from .runtime import model_call


class DemoProvider:
    name = "local_stub"

    def json(self, *, role, tier, system, user, max_tokens=800, reasoning_effort=None):
        def respond():
            time.sleep(0.2)
            if role == "planner":
                return {
                    "affective_state": "curious",
                    "affect_reasoning": "Synthetic demo",
                    "intervention": "co_reason",
                    "target_concept": "g",
                    "planner_note": "Synthetic check",
                    "confidence": 0.8,
                }
            if role == "reasoner":
                return {
                    "message": "Local model stub: what is the next small step you could check?",
                    "check_question": None,
                    "confidence": 0.8,
                    "grasped": [],
                    "shaky": [],
                }
            return {
                "needs_revision": False,
                "confidence": 0.8,
                "leak_risk": "none",
                "self_critique": "Synthetic check",
                "reasons": [],
                "flagged": False,
                "score": 0.0,
            }

        return model_call(respond, system + user, max_tokens, lambda _: (10, 5))


def initialize(engine, directory: Path):
    from ..agent import llm
    from ..config import settings

    key = directory / "execution.key"
    if not key.exists():
        fd = os.open(key, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, Fernet.generate_key())
        finally:
            os.close(fd)
    Fernet(key.read_bytes().strip())
    Ledger(engine).initialize(
        Policy(
            version="local-stub-v1",
            price_version="synthetic-zero",
            currency="USD",
            input_price=0,
            output_price=0,
            deployment=Limits(tokens=1000000000),
            institution=Limits(),
            classroom=Limits(),
            learner=Limits(),
        )
    )
    # All existing imported factory aliases consult this registry at construction.
    # Even optional secondary model guards receive the stub in this explicit mode.
    settings.provider = "openai_compatible"
    llm._PROVIDERS["openai_compatible"] = DemoProvider


def start_worker():
    from ..agent import get_llm
    from ..config import settings
    from ..core.registry import get_active_pack
    from ..store import ConsentRouter, SqlStore
    from .jobs_http import execution_store
    from .jobs_worker import AskAdapter
    from .worker import run_one

    if settings.belay_env != "local":
        raise ValueError("synthetic worker requires the explicit local host")
    stopped = threading.Event()
    store = execution_store()
    adapter = AskAdapter(store, ConsentRouter(SqlStore()), get_active_pack(), get_llm)

    def work():
        while not stopped.is_set():
            try:
                adapter.cleanup()
                if run_one(store.admission, adapter):
                    continue
            except ControlError:
                pass
            stopped.wait(0.2)

    thread = threading.Thread(target=work, name="saved-ask-demo-worker", daemon=True)
    thread.start()
    return stopped, thread
