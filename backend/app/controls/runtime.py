# SPDX-License-Identifier: AGPL-3.0-only
"""One operation context propagates through model and runner safety work."""

from __future__ import annotations

import contextvars
import math
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, TypeVar

from ..config import settings
from .contracts import Amount, ControlError, Scope
from .ledger import Ledger

T = TypeVar("T")


@dataclass(frozen=True)
class Execution:
    ledger: Ledger
    scope: Scope
    operation: str


_execution: contextvars.ContextVar[Execution | None] = contextvars.ContextVar(
    "control_execution", default=None
)


@contextmanager
def operation(ledger: Ledger, scope: Scope, operation_id: str) -> Iterator[None]:
    scope.keys()
    token = _execution.set(Execution(ledger, scope, operation_id))
    try:
        yield
    finally:
        _execution.reset(token)


def current() -> Execution | None:
    context = _execution.get()
    if context is not None:
        return context
    if settings.controls_mode == "development_bypass":
        return None
    if settings.controls_mode != "enforced":
        raise ControlError("invalid_controls_mode", 503)
    raise ControlError("verified_execution_required", 503)


def model_call(
    call: Callable[[], T],
    input_text: str,
    output_limit: int,
    usage: Callable[[T], tuple[int | None, int | None]],
) -> T:
    context = current()
    if context is None:
        return call()
    if output_limit <= 0:
        raise ControlError("invalid_output_bound", 503)
    # UTF-8 bytes plus explicit framing allowance. An operational estimate,
    # not a provider invoice guarantee. Thinking is included in output_limit.
    input_bound = len(input_text.encode("utf-8")) + 1024
    with context.ledger.transaction() as conn:
        policy = context.ledger.policy(conn)
    attempt_id = uuid.uuid4().hex
    row = context.ledger.reserve(
        attempt_id,
        context.operation,
        context.scope,
        Amount(
            tokens=input_bound + output_limit,
            microunits=input_bound * policy.input_price + output_limit * policy.output_price,
        ),
        "model",
    )
    if row["policy"] != policy.model_dump():
        context.ledger.settle(attempt_id, Amount())
        raise ControlError("policy_changed", 503)
    try:
        result = call()
        prompt, completion = usage(result)
    except BaseException:
        # A lost response or interrupted thread is not proof of zero usage.
        context.ledger.settle(attempt_id, None)
        raise
    if type(prompt) is not int or type(completion) is not int or prompt < 0 or completion < 0:
        context.ledger.settle(attempt_id, None)
    else:
        context.ledger.settle(
            attempt_id,
            Amount(
                tokens=prompt + completion,
                microunits=prompt * policy.input_price + completion * policy.output_price,
            ),
        )
    return result


def runner_call(call: Callable[[], T], wall_seconds: float) -> T:
    context = current()
    if context is None:
        return call()
    if not math.isfinite(wall_seconds) or wall_seconds <= 0:
        raise ControlError("invalid_runner_bound", 503)
    attempt_id = uuid.uuid4().hex
    context.ledger.reserve(
        attempt_id,
        context.operation,
        context.scope,
        Amount(runs=1, wall_ms=math.ceil(wall_seconds * 1000)),
        "runner",
    )
    try:
        result = call()
    except BaseException:
        context.ledger.settle(attempt_id, None)
        raise
    # Runner completion includes timeout/kill; no optimistic refund on errors.
    measured: Any = getattr(result, "wall_ms", None)
    context.ledger.settle(
        attempt_id,
        Amount(runs=1, wall_ms=math.ceil(measured))
        if isinstance(measured, (int, float)) and math.isfinite(measured) and measured >= 0
        else None,
    )
    return result
