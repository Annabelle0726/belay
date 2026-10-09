# SPDX-License-Identifier: AGPL-3.0-only
"""Content-free errors for both HTTP surfaces, including embedded Quad routers."""

from fastapi import HTTPException

from .contracts import ControlError


def control_http_error(exc: ControlError) -> HTTPException:
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after is not None else {}
    return HTTPException(exc.status, {"code": exc.code}, headers=headers)
