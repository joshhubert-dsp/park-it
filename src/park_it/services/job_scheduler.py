from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.util import undefined
from pydantic import AwareDatetime


class JobScheduler:
    """Wrapper around the APScheduler for scheduled function calls."""

    def __init__(self, scheduler: AsyncIOScheduler) -> None:
        self._scheduler = scheduler

    def schedule_single_dt(
        self,
        job_id: str,
        run_dt: AwareDatetime,
        callback: Callable[..., Any],
        *,
        callback_kwargs: dict[str, Any],
    ) -> None:
        """run_dt must be UTC-zoned datetime (not naive)"""
        assert run_dt.tzinfo is not None
        self._scheduler.add_job(
            func=callback,
            trigger="date",
            id=job_id,
            kwargs=callback_kwargs,
            replace_existing=True,
            misfire_grace_time=None,
            coalesce=True,
            # trigger kwargs
            run_date=run_dt,
            # timezone=self._timezone,
        )

    def schedule_minutes_interval(
        self,
        job_id: str,
        minutes: int,
        start_dt: AwareDatetime | None,
        num_runs: int | None,
        first_no_wait: bool,
        callback: Callable[..., Any],
        *,
        callback_kwargs: dict[str, Any],
    ) -> None:
        """run_dt must be UTC-zoned datetime (not naive)"""
        if start_dt is None:
            start_dt = datetime.now(UTC)
        else:
            assert start_dt.tzinfo is not None

        end_dt = None
        if num_runs is not None:
            end_dt = start_dt + timedelta(minutes=minutes * num_runs + 1)

        self._scheduler.add_job(
            func=callback,
            trigger="interval",
            id=job_id,
            kwargs=callback_kwargs,
            replace_existing=True,
            misfire_grace_time=None,
            coalesce=True,
            next_run_time=start_dt if first_no_wait else undefined,
            # trigger kwargs
            minutes=minutes,
            start_date=start_dt,
            end_date=end_dt,
        )

    def cancel(self, job_id: str) -> None:
        try:
            self._scheduler.remove_job(job_id)
        except JobLookupError:
            pass

    def shutdown(self, wait: bool = False) -> None:
        self._scheduler.shutdown(wait=wait)
