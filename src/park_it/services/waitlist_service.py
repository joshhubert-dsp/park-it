from __future__ import annotations

from datetime import UTC, datetime, timedelta

from loguru import logger

from park_it.app.dependencies import (
    AppDependencies,
    ScheduledJobContext,
    get_emailer,
    get_jinja_env,
    get_space_state_db,
    get_wait_an_db,
    get_wait_tn_db,
)
from park_it.models.space import SpaceModel, SpaceState, SpaceType
from park_it.models.waitlist import WaitlistEntry

# TODO why does this service lend itself better to a functional style than the others?
# It's more complex / cross-resource, probably part of it


def handle_waitlist_notification(
    updated_space: SpaceModel, deps: AppDependencies, job_ctx: ScheduledJobContext
) -> None:
    # previous_space: SpaceModel,

    assert deps.wait_deps is not None
    wait_deps = deps.wait_deps

    # previous_state = previous_space.state
    sensor_id = updated_space.sensor_id
    assert updated_space.type is not None

    if updated_space.state is SpaceState.FREE:
        # and previous_state is SpaceState.OCCUPIED:
        num_waiting = wait_deps.to_notify_db.count(updated_space.type)
        if num_waiting == 0:
            logger.info(
                f"{sensor_id}: no waitlist entries for space type {updated_space.type}"
            )
            return

        start_dt = datetime.now(tz=UTC) + timedelta(
            minutes=deps.config.waitlist_free_debounce_minutes
        )
        logger.info(
            f"{sensor_id}: space free occupied, scheduling waitlist interval notify job for {start_dt.isoformat(timespec='seconds')}"
        )

        wait_deps.job_scheduler.schedule_minutes_interval(
            job_id=sensor_id,
            minutes=deps.config.waitlist_interval_minutes,
            start_dt=start_dt,
            num_runs=num_waiting,
            first_no_wait=True,
            callback=cb_notify_next_entry_free,
            callback_kwargs={"sensor_id": sensor_id, "job_ctx": job_ctx},
        )

    elif updated_space.state is SpaceState.OCCUPIED:
        #   and previous_state is SpaceState.FREE
        # If the space is now occupied, cancel the interval waitlist pop/alert job
        logger.info(
            f"{sensor_id}: space now occupied, canceling waitlist interval notify job"
        )
        wait_deps.job_scheduler.cancel(sensor_id)

        if deps.space_state_db.count(type=updated_space.type, only_free=True) == 0:
            notify_all_spaces_now_occupied(updated_space.type, deps)


async def cb_notify_next_entry_free(
    sensor_id: str, job_ctx: ScheduledJobContext
) -> None:
    """
    This is the interval scheduled job callback.
    `handle_waitlist_notification()` handles the final user notification on
    re-occupied. The state check here serves as both the debounce on initial space freeing
    (ensures the FREE signal isn't just someone backing out to align their car in the
    space), and also as a safeguard to avoid race conditions between a scheduled job
    process and app-process running handle_waitlist_notification.
    """
    space_state_db = get_space_state_db(job_ctx.sqlite_dir, job_ctx.config.db_echo)
    space = space_state_db.get(sensor_id)
    assert space is not None
    if space.state is SpaceState.OCCUPIED:
        logger.info(
            f"{sensor_id}: notify_next_entry_free check -> OCCUPIED, skipping notify"
        )
        return

    _cb_notify_next_entry_free_inner(space, job_ctx)


def _cb_notify_next_entry_free_inner(
    space: SpaceModel, job_ctx: ScheduledJobContext
) -> WaitlistEntry | None:
    wait_tn_db = get_wait_tn_db(job_ctx.sqlite_dir, job_ctx.config.db_echo)
    entry = wait_tn_db.pop(space.type)
    if entry is None:
        logger.info(f"wait_tn_db has no entries to pop for space type {space.type}")
        return None

    emailer = get_emailer(job_ctx.google_token_path)
    jinja_env = get_jinja_env()

    delivered = emailer.notify_free_space(entry, job_ctx.config, jinja_env)
    if not delivered:
        delivered = emailer.notify_free_space(entry, job_ctx.config, jinja_env)
        if not delivered:
            logger.info(
                f"free email to {entry.email} failed on second attempt, giving up"
            )

    wait_an_db = get_wait_an_db(job_ctx.sqlite_dir, job_ctx.config.db_echo)
    wait_an_db.insert(_clone_waitlist_entry(entry))

    return entry


def notify_all_spaces_now_occupied(
    space_type: SpaceType, deps: AppDependencies
) -> None:
    assert deps.wait_deps is not None
    wait_deps = deps.wait_deps

    failed_entries: list[WaitlistEntry] = []

    while True:
        entry = wait_deps.notified_db.pop(space_type)
        if entry is None:
            break

        delivered = wait_deps.emailer.notify_space_now_occupied(
            entry, deps.config, deps.templates.env
        )
        if not delivered:
            failed_entries.append(entry)

    for entry in failed_entries:
        delivered = wait_deps.emailer.notify_space_now_occupied(
            entry, deps.config, deps.templates.env
        )
        if not delivered:
            logger.info(
                f"occupied email to {entry.email} failed on second attempt, giving up"
            )


def _clone_waitlist_entry(entry: WaitlistEntry) -> WaitlistEntry:
    return WaitlistEntry.model_validate(entry.model_dump(exclude={"id"}))
