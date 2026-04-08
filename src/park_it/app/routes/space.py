from __future__ import annotations

from inspect import signature
from typing import Annotated, NamedTuple

import numpy as np
from fastapi import APIRouter, Request
from fastapi.params import Depends
from fastapi.responses import HTMLResponse
from loguru import logger
from sse_starlette import EventSourceResponse

from park_it.app.dependencies import (
    AppDependencies,
    ScheduledJobContext,
)
from park_it.app.utils import (
    get_app_deps,
    get_dep,
    get_job_ctx,
)
from park_it.models.space import SpaceState, SpaceType, SpaceUsage
from park_it.models.space_update import SpaceUpdateBaseModel
from park_it.services.db.space_usage_db import SpaceUsageDatabase
from park_it.services.sse_handler import SSEHandler
from park_it.services.waitlist_service import handle_waitlist_notification

SPACE_RESPONSE_TEMPLATE = "site/space_states.html.j2"


class MedianSpaceUsageDuration(NamedTuple):
    occupied: float
    free: float


DEBUG_COMPUTE_MEAN = True


def _compute_space_usage(
    type: SpaceType,
    space_usage_db: SpaceUsageDatabase,
    usage_median_num: int,
    num_spaces: int,
    wait_len: int | None,
) -> tuple[MedianSpaceUsageDuration | None, float | None]:
    all_occupied = space_usage_db.get(
        n_newest=usage_median_num, state=SpaceState.OCCUPIED, type=type
    )
    all_free = space_usage_db.get(
        n_newest=usage_median_num, state=SpaceState.FREE, type=type
    )

    if not all_occupied or not all_free:
        # if there are no entries for time occupied/free for this space type so far
        return None, None

    occupied_med = float(np.median([occ.duration_sec for occ in all_occupied]))
    free_med = float(np.median([free.duration_sec for free in all_free]))
    logger.debug(
        f"{type} num for median - occupied: {len(all_occupied)}, free: {len(all_free)}"
    )
    logger.debug(f"{type} median - occupied: {occupied_med}, free: {free_med}")

    if DEBUG_COMPUTE_MEAN:
        occupied_mean = float(np.mean([occ.duration_sec for occ in all_occupied]))
        free_mean = float(np.mean([free.duration_sec for free in all_free]))
        logger.debug(f"{type} mean - occupied: {occupied_mean}, free: {free_mean}")

    median_usage = MedianSpaceUsageDuration(occupied_med, free_med)

    if wait_len is not None and num_spaces > 0:
        wait_time = wait_len * (median_usage.occupied + median_usage.free) / num_spaces
    else:
        wait_time = None

    return median_usage, wait_time


def _build_space_state_context(deps: AppDependencies) -> dict[str, object]:
    """Collect the latest status data used by both HTTP and SSE responses."""
    free_spaces: dict[SpaceType, int] = {}
    median_usage: dict[SpaceType, MedianSpaceUsageDuration] = {}
    wait_lens: dict[SpaceType, int] = {}
    wait_times: dict[SpaceType, float] = {}

    for t in deps.config.space_types:
        free_spaces[t] = deps.space_state_db.count(t, only_free=True)
        if deps.wait_deps is not None:
            wait_lens[t] = deps.wait_deps.to_notify_db.count(t)

        if deps.space_usage_db is not None:
            med, wait_t = _compute_space_usage(
                t,
                deps.space_usage_db,
                deps.config.usage_median_num,
                deps.config.space_counter[t],
                wait_lens.get(t),
            )
            if med is not None:
                median_usage[t] = med
            if wait_t is not None:
                wait_times[t] = wait_t

    # Optional full status list for dashboards that show each individual sensor.
    space_states = []
    if deps.config.show_individual_spaces:
        for space in deps.config.spaces:
            space_states.append(deps.space_state_db.get(space.sensor_id))

    return {
        "total_spaces": deps.config.space_counter,
        "free_spaces": free_spaces,
        "median_usage": median_usage,
        "wait_lens": wait_lens,
        "wait_times": wait_times,
        "space_states": space_states,
    }


def _create_update_space_state_endpoint(
    space_update_model: type[SpaceUpdateBaseModel],
):
    async def update_space_state(
        request: SpaceUpdateBaseModel,  # typehint gets redefined with the user's passed model
        deps: Annotated[AppDependencies, Depends(get_app_deps)],
        job_ctx: Annotated[ScheduledJobContext, Depends(get_job_ctx)],
    ):
        # logger.debug(pformat(request))

        prev_space = deps.space_state_db.get(request.sensor_id())
        updated_space = deps.space_state_db.upsert(request.to_model())

        if updated_space.state is not SpaceState.OUT_OF_ORDER:
            if deps.space_usage_db is not None and (
                # guard against a missed update throwing off the usage data
                prev_space.state != updated_space.state
            ):
                space_usage = SpaceUsage.from_space_models(updated_space, prev_space)
                deps.space_usage_db.insert(space_usage)

            if deps.config.waitlist:
                # waitlist notifications that space state has changed
                handle_waitlist_notification(updated_space, deps, job_ctx)

        # Broadcast the refreshed HTML fragment so connected clients can update
        # their status widgets immediately, without polling.
        if deps.sse_handler is not None:
            status_context = _build_space_state_context(deps)
            template = deps.templates.get_template(SPACE_RESPONSE_TEMPLATE)
            status_html = template.render(status_context)
            await deps.sse_handler.publish(status_html, event="message")

    original_signature = signature(update_space_state)
    request_param = next(iter(original_signature.parameters.values()))
    updated_params = [
        request_param.replace(annotation=space_update_model),
        *list(original_signature.parameters.values())[1:],
    ]
    update_space_state.__signature__ = original_signature.replace(  # pyright: ignore[reportFunctionMemberAccess]
        parameters=updated_params
    )
    update_space_state.__annotations__["request"] = space_update_model
    return update_space_state


async def stream_space_events(
    sse_handler: Annotated[SSEHandler, Depends(get_dep("sse_handler"))],
) -> EventSourceResponse:
    """Open the live SSE stream consumed by HTMX `sse-connect`."""
    return sse_handler.response(ping_seconds=1)


async def get_space_states(
    request: Request, deps: Annotated[AppDependencies, Depends(get_app_deps)]
):
    status_context = _build_space_state_context(deps)
    return deps.templates.TemplateResponse(
        request,
        name=SPACE_RESPONSE_TEMPLATE,
        context=status_context,
    )


def create_space_router(
    space_update_model: type[SpaceUpdateBaseModel],
) -> APIRouter:
    """this defines the /space/update-state endpoint dynamically, inserting the user's
    space_update_model class as the expected request model in the function signature, to
    allow for proper fastapi/pydantic validation"""
    router = APIRouter(prefix="/space")
    update_space_state = _create_update_space_state_endpoint(space_update_model)

    router.add_api_route("/update-state", endpoint=update_space_state, methods=["POST"])
    router.add_api_route(
        "/events",
        endpoint=stream_space_events,
        methods=["GET"],
        response_class=EventSourceResponse,
    )
    router.add_api_route(
        "/get-states-html",
        endpoint=get_space_states,
        methods=["GET"],
        response_class=HTMLResponse,
    )
    return router
