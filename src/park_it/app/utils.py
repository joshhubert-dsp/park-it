from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from devtools import pformat
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import ValidationError

if TYPE_CHECKING:
    from park_it.app.dependencies import (
        AppDependencies,
        ScheduledJobContext,
        WaitlistDependencies,
    )


def get_place_int_suffix(place: int) -> str:
    """Return English ordinal suffix for a positive integer (1st, 2nd, ...)."""
    if place % 10 == 1 and place % 100 != 11:
        return "st"
    if place % 10 == 2 and place % 100 != 12:
        return "nd"
    if place % 10 == 3 and place % 100 != 13:
        return "rd"
    return "th"


SECONDS_IN_MINUTE = 60
SECONDS_IN_HOUR = SECONDS_IN_MINUTE * 60
SECONDS_IN_DAY = SECONDS_IN_HOUR * 24


def duration_str(seconds: float) -> str:
    if seconds >= SECONDS_IN_DAY:
        return f"{seconds / SECONDS_IN_DAY:.1f} days"
    elif seconds >= SECONDS_IN_HOUR:
        return f"{seconds / SECONDS_IN_HOUR:.1f} hours"
    else:
        return f"{seconds // SECONDS_IN_MINUTE:.0f} minutes"


# --- APP SINGLETON/CONSTANT GETTERS W/ TYPE HINTING ---


def get_dep(name: str) -> Callable[[Request], Any]:
    """fastapi implicitly attaches the request object when it sees the Request typehint"""

    def dependency(request: Request) -> Any:
        return getattr(request.app.state.deps, name)

    return dependency


def get_app_deps(request: Request) -> AppDependencies:
    return request.app.state.deps


def get_wait_deps(request: Request) -> WaitlistDependencies:
    wait_deps = request.app.state.deps.wait_deps
    assert wait_deps is not None
    return wait_deps


def get_job_ctx(request: Request) -> ScheduledJobContext:
    return request.app.state.job_ctx


# --- APP LOGGING EXCEPTION HANDLERS ---


async def log_request_validation_error(
    request: Request, exc: RequestValidationError, log_payload: bool = True
):
    logger.error(
        f"RequestValidationError during {request.method} {request.url.path}: {exc.errors()}"
    )
    if log_payload:
        payload = await request.json()
        logger.error(pformat(payload))

    return JSONResponse(
        content={"detail": "bad request payload"},
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )
    # return await request_validation_exception_handler(request, exc)


async def handle_validation_error(request: Request, exc: ValidationError):
    """just using this for now to report both request and response model validation
    failure. in prod, should probably remove and allow for default server error 500 for
    response error"""
    logger.exception(
        f"ValidationError during {request.method} {request.url.path}: {exc.errors()}"
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": "\n".join([e["msg"] for e in exc.errors()])},
    )


async def log_unexpected_exception(request: Request, exc: Exception):
    logger.exception(
        f"An unexpected error occurred during {request.method} {request.url.path}: {exc}"
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
