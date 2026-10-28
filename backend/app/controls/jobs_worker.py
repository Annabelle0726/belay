# SPDX-License-Identifier: AGPL-3.0-only
"""Actual unsaved Ask adapter. Run explicitly: python -m app.controls.jobs_worker.

No in-process HTTP background queue, token replay or automatic retry of unknown
jobs. Provider calls stay inside the existing controls runtime and tutor loop.
"""

from __future__ import annotations

import argparse
import json
import logging
import threading
import time
from collections.abc import Callable

from fastapi import HTTPException

from ..agent import Provider, get_llm, run_turn
from ..agent.orchestrator import _distress_turn
from ..config import settings
from ..conversations.bounds import BoundedProvider
from ..core.registry import get_active_pack
from ..pedagogy import authorized_turn
from ..store import ConsentRouter, InMemoryStore, SqlStore
from ..store.scoped import scoped_store
from . import saved
from .contracts import ControlError, Scope
from .data import ExecutionData
from .jobs_http import execution_store
from .runtime import current
from .worker import run_one


class _LazyProvider:
    def __init__(self, factory: Callable[[], Provider]):
        self.factory = factory
        self.name: str = settings.provider
        self.instance: Provider | None = None

    def json(self, **kwargs) -> dict:
        current()  # Recheck before even constructing the SDK/provider.
        if self.instance is None:
            self.instance = self.factory()
        return self.instance.json(**kwargs)


class AskAdapter:
    def __init__(
        self, store: ExecutionData, router: ConsentRouter, pack, llm_factory: Callable[[], Provider]
    ):
        self.store, self.router, self.pack = store, router, pack
        self.llm = _LazyProvider(llm_factory)

    def check(self, job: dict) -> Scope:
        try:
            identity, payload = self.store.load(job)
        except HTTPException as exc:
            raise ControlError(
                "authorization_revoked" if exc.status_code == 404 else "authorization_unavailable",
                exc.status_code,
            ) from None
        if (
            payload.get("exercise_id") != identity.exercise_id
            or payload.get("participant_id") != identity.learner_id
        ):
            raise ControlError("job_unavailable", 404)
        try:
            self.pack.get_exercise(identity.exercise_id)
        except KeyError:
            raise ControlError("assignment_unavailable", 404) from None
        return self.store.scope(identity)

    def execute(self, job: dict) -> str:
        self.check(job)
        identity, payload = self.store.load(job)
        payload, policy = saved.begin(
            self.store, job, identity, {**payload, "_persona": self.pack.persona.id}
        )
        exercise = self.pack.get_exercise(identity.exercise_id)
        # R1 consent routing and scoped content-free traces are unchanged.
        store = scoped_store(self.router, identity)
        if payload.get("_support"):
            response = _distress_turn(
                {},
                store,
                identity.learner_id,
                exercise,
                payload.get("mode", "study"),
                payload.get("stance", "peer"),
                self.pack,
            )
        else:
            response = authorized_turn(
                run_turn,
                {**payload, "exercise": exercise},
                BoundedProvider(self.llm, policy) if policy else self.llm,
                store,
                identity,
            )
        self.check(job)
        return self.store.stage(job, response)

    def publish(self, job: dict, result_ref: str) -> None:
        self.check(job)
        self.store.publish(job, result_ref)

    def cleanup(self) -> None:
        self.store.cleanup()


def start_worker(*, poll_seconds: float = 0.2):
    """Managed API+worker host. No provider override, schema creation or replay.

    Fatal errors stop the thread so the host supervisor can stop admission.
    Temporary control denials keep their existing conservative ledger behavior.
    """
    from ..conversations.policy import Policy as DialoguePolicy
    from ..conversations.repository import ConversationStore

    store = execution_store()
    router = ConsentRouter(SqlStore() if settings.store_backend == "sql" else InMemoryStore())
    adapter = AskAdapter(store, router, get_active_pack(), get_llm)
    history = ConversationStore(store.ledger.engine, DialoguePolicy.from_settings(settings))
    stopped = threading.Event()

    def work():
        next_cleanup = 0.0
        try:
            while not stopped.is_set():
                try:
                    adapter.cleanup()
                    if time.monotonic() >= next_cleanup:
                        history.cleanup()  # Also applies when optional saving is disabled.
                        next_cleanup = time.monotonic() + 30
                    if run_one(store.admission, adapter):
                        continue
                except ControlError:
                    pass
                stopped.wait(poll_seconds)
        except Exception:
            logging.getLogger(__name__).error("controlled_worker_stopped")

    thread = threading.Thread(target=work, name="controlled-ask-worker", daemon=True)
    thread.start()
    return stopped, thread


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=int, choices=range(1, 61), default=1)
    args = parser.parse_args(argv)
    try:
        store = execution_store()
        router = ConsentRouter(SqlStore() if settings.store_backend == "sql" else InMemoryStore())
        adapter = AskAdapter(store, router, get_active_pack(), get_llm)
        while True:
            adapter.cleanup()
            worked = run_one(store.admission, adapter)
            if args.once:
                print(json.dumps({"claimed": worked}))
                return 0
            if not worked:
                time.sleep(args.poll_seconds)
    except (ControlError, HTTPException, ValueError, OSError):
        print(json.dumps({"error": "worker_unavailable"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
