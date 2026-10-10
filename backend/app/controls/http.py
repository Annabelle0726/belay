# SPDX-License-Identifier: AGPL-3.0-only
"""Content-free errors for both HTTP surfaces, including embedded Quad routers."""

from fastapi import HTTPException

from .contracts import ControlError


def control_http_error(exc: ControlError) -> HTTPException:
    headers = {
        "Cache-Control": "no-store",
        "Vary": "Authorization, X-Belay-Institution, X-Belay-Class",
    }
    if exc.retry_after is not None:
        headers["Retry-After"] = str(exc.retry_after)
    return HTTPException(exc.status, {"code": exc.code}, headers=headers)
