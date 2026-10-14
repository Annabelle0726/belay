# SPDX-License-Identifier: AGPL-3.0-only
"""One operation context propagates through model and runner safety work."""

from __future__ import annotations

import contextvars
import logging
import math
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, TypeVar

from ..config import settings
from .admission import Admission
from .contracts import Amount, ControlError, Scope
from .ledger import Ledger

T = TypeVar("T")


@dataclass(frozen=True)
class Execution:
    ledger: Ledger
    scope: Scope
    operation: str
    guard: Callable[[], None] | None = None


_execution: contextvars.ContextVar[Execution | None] = contextvars.ContextVar(
    "control_execution", default=None
)


@contextmanager
def operation(
    ledger: Ledger, scope: Scope, operation_id: str, guard: Callable[[], None] | None = None
) -> Iterator[None]:
    scope.keys()
    token = _execution.set(Execution(ledger, scope, operation_id, guard))
    try:
        yield
    finally:
        _execution.reset(token)


def current() -> Execution | None:
    context = _execution.get()
    if context is not None:
        if context.guard:
            context.guard()
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
        if settings.llm_billing_mode not in {"metered", "unmetered"}:
            raise ControlError("invalid_billing_mode", 503)
        if settings.llm_billing_mode == "metered" and (
            policy.input_price <= 0 or policy.output_price <= 0
        ):
            raise ControlError("model_price_unavailable", 503)
        check_inference_deadline(context.ledger.now(conn))
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
    admission = Admission(context.ledger)
    try:
        slot = admission.acquire_slot(context.scope, context.operation, "model")
    except BaseException:
        context.ledger.settle(attempt_id, Amount())
        raise
    try:
        if context.guard:
            context.guard()
        if settings.controls_inference_expires_at:
            with context.ledger.transaction() as conn:
                check_inference_deadline(context.ledger.now(conn))
    except BaseException:
        admission.release_slot(slot, stopped=True)
        context.ledger.settle(attempt_id, Amount())
        raise
    try:
        result = call()
        prompt, completion = usage(result)
    except BaseException as exc:
        # A lost response or interrupted thread is not proof of zero usage.
        context.ledger.settle(attempt_id, None)
        # An explicit authentication/format rejection is a finished request,
        # not a possibly running call. Keep unknown usage reserved separately.
        status = getattr(exc, "status_code", None)
        rejected_auth = type(status) is int and status in {401, 403}
        admission.release_slot(slot, stopped=rejected_auth or status in {400, 422})
        category = (
            "provider_auth_failed"
            if rejected_auth
            else (
                "provider_timeout"
                if isinstance(exc, TimeoutError) or type(exc).__name__ == "APITimeoutError"
                else "provider_connection_failed"
                if type(exc).__name__ == "APIConnectionError"
                else "provider_call_failed"
            )
        )
        # Content-free incident evidence: no exception text, URL, key or prompt.
        logging.getLogger(__name__).warning(
            "model_call_failed operation=%s attempt=%s category=%s http_status=%s",
            context.operation,
            attempt_id,
            category,
            status if type(status) is int else None,
        )
        if rejected_auth:
            raise ControlError("provider_auth_failed", 503) from None
        raise
    admission.release_slot(slot, stopped=True)
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


def check_inference_deadline(now: float) -> None:
    deadline = settings.controls_inference_expires_at
    if not math.isfinite(deadline) or deadline < 0:
        raise ControlError("invalid_inference_window", 503)
    if deadline and now >= deadline:
        raise ControlError("inference_window_expired", 503)


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
        # Include a small accounting allowance for timeout/kill overhead;
        # actual excess is still recorded and stops further spending.
        Amount(runs=1, wall_ms=math.ceil(wall_seconds * 1000) + 1000),
        "runner",
    )
    admission = Admission(context.ledger)
    try:
        slot = admission.acquire_slot(context.scope, context.operation, "runner")
    except BaseException:
        context.ledger.settle(attempt_id, Amount())
        raise
    try:
        if context.guard:
            context.guard()
    except BaseException:
        admission.release_slot(slot, stopped=True)
        context.ledger.settle(attempt_id, Amount())
        raise
    try:
        result = call()
    except BaseException:
        context.ledger.settle(attempt_id, None)
        admission.release_slot(slot, stopped=False)
        raise
    admission.release_slot(slot, stopped=True)
    # Runner completion includes timeout/kill; no optimistic refund on errors.
    measured: Any = getattr(result, "wall_ms", None)
    context.ledger.settle(
        attempt_id,
        Amount(runs=1, wall_ms=math.ceil(measured))
        if isinstance(measured, (int, float)) and math.isfinite(measured) and measured >= 0
        else None,
    )
    return result
