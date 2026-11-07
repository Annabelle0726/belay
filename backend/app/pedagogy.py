# SPDX-License-Identifier: AGPL-3.0-only
"""Request-local permission checks; never put identity or callbacks in model context."""

from collections.abc import Callable
from contextvars import ContextVar

from .auth import Identity, recheck_behavior

_check: ContextVar[Callable[[], None] | None] = ContextVar("belay_behavior_check", default=None)


def check_current() -> None:
    check = _check.get()
    if check is not None:
        check()


class AuthorizedProvider:
    def __init__(self, provider):
        self.provider = provider
        self.name = getattr(provider, "name", "test")

    def json(self, **kwargs) -> dict:
        check_current()
        result: dict = self.provider.json(**kwargs)
        check_current()
        return result


def authorized_turn(tutor, payload: dict, provider, store, identity: Identity) -> dict:
    mode, stance = payload.get("mode", "study"), payload.get("stance", "peer")
    token = _check.set(lambda: recheck_behavior(identity, mode, stance))
    try:
        check_current()
        result: dict = tutor(
            payload, AuthorizedProvider(provider) if provider is not None else None, store
        )
        check_current()
        return result
    finally:
        _check.reset(token)
