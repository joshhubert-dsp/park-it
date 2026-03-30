from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC
from functools import lru_cache
from pathlib import Path
from typing import Self

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi.templating import Jinja2Templates
from jinja2 import (
    Environment,
    PackageLoader,
    select_autoescape,
)
from pydantic import DirectoryPath, FilePath

from park_it.app.utils import duration_str, get_place_int_suffix
from park_it.models.app_config import AppConfig
from park_it.models.space import get_space_type_emoji
from park_it.services.db.database import (
    SPACE_STATE_DB_FILE_PREFIX,
    SPACE_USAGE_DB_FILE_PREFIX,
    WAITLIST_NOTIFIED_DB_FILE_PREFIX,
    WAITLIST_TO_NOTIFY_DB_FILE_PREFIX,
    init_db,
)
from park_it.services.db.space_state_db import SpaceStateDatabase
from park_it.services.db.space_usage_db import SpaceUsageDatabase
from park_it.services.db.waitlist_db import WaitlistDatabase
from park_it.services.email.emailer import Emailer, PrintDebugEmailer
from park_it.services.email.gmailer import Gmailer, init_gmail
from park_it.services.job_scheduler import JobScheduler
from park_it.services.sse_handler import SSEHandler

# NOTE: these functions are cached because they return immutable service objects used by
# the separate scheduled job contexts as well


@lru_cache(maxsize=1)
def get_jinja_env() -> Environment:
    env = Environment(
        loader=PackageLoader("park_it", "templates"),
        autoescape=select_autoescape(["html", "xml"]),
    )
    # handy '|' filter functions
    env.filters["emoji"] = get_space_type_emoji
    env.filters["get_place_int_suffix"] = get_place_int_suffix
    env.filters["duration_str"] = duration_str
    return env


@lru_cache(maxsize=1)
def get_emailer(google_token_path: FilePath | None = None) -> Emailer:
    if os.getenv("DEBUG_EMAILER"):
        return PrintDebugEmailer()
    elif google_token_path is None:
        raise Exception(
            "`google_token_path` is required to set up a functional email waitlist. "
            "If you want to test with the PrintDebugEmailer instead, set the env var `DEBUG_EMAILER`."
        )
    return Gmailer(init_gmail(google_token_path))


@lru_cache(maxsize=1)
def get_space_state_db(sqlite_dir: Path, db_echo: bool = True) -> SpaceStateDatabase:
    return init_db(sqlite_dir, SPACE_STATE_DB_FILE_PREFIX, SpaceStateDatabase, db_echo)


@lru_cache(maxsize=1)
def get_space_usage_db(sqlite_dir: Path, db_echo: bool = True) -> SpaceUsageDatabase:
    return init_db(sqlite_dir, SPACE_USAGE_DB_FILE_PREFIX, SpaceUsageDatabase, db_echo)


@lru_cache(maxsize=1)
def get_wait_tn_db(sqlite_dir: Path, db_echo: bool = True) -> WaitlistDatabase:
    return init_db(
        sqlite_dir, WAITLIST_TO_NOTIFY_DB_FILE_PREFIX, WaitlistDatabase, db_echo
    )


@lru_cache(maxsize=1)
def get_wait_an_db(sqlite_dir: Path, db_echo: bool = True) -> WaitlistDatabase:
    return init_db(
        sqlite_dir, WAITLIST_NOTIFIED_DB_FILE_PREFIX, WaitlistDatabase, db_echo
    )


@dataclass
class WaitlistDependencies:
    to_notify_db: WaitlistDatabase
    notified_db: WaitlistDatabase
    job_scheduler: JobScheduler
    emailer: Emailer
    password: str


@dataclass
class AppDependencies:
    """all active application dependencies, stored in app.state and accessed with Depends()"""

    config: AppConfig
    templates: Jinja2Templates
    space_state_db: SpaceStateDatabase
    space_usage_db: SpaceUsageDatabase | None
    sse_handler: SSEHandler | None = None
    wait_deps: WaitlistDependencies | None = None

    @classmethod
    def initialize(
        cls,
        config: AppConfig,
        sqlite_dir: DirectoryPath,
        google_token_path: FilePath | None,
        waitlist_password_path: FilePath | None,
    ) -> Self:

        space_state_db = get_space_state_db(sqlite_dir, config.db_echo)
        # load space info into db
        for space in config.spaces:
            space_state_db.initial_insert(space.to_model())

        if config.store_usage_durations:
            space_usage_db = get_space_usage_db(sqlite_dir, config.db_echo)
        else:
            space_usage_db = None

        if config.waitlist:
            pw: str | None = None
            if waitlist_password_path is not None:
                pw = waitlist_password_path.read_text("utf8")
            else:
                pw = os.getenv("PARK_IT_WAITLIST_PASSWORD")
            if pw is None:
                raise RuntimeError(
                    "Since you have activated email waitlist functionality, you must "
                    "set a shared password for the waitlist form using either the "
                    "argument `waitlist_password_path` or the "
                    "enviroment variable `PARK_IT_WAITLIST_PASSWORD`."
                )

            wait_tn_db = get_wait_tn_db(sqlite_dir, config.db_echo)
            wait_an_db = get_wait_an_db(sqlite_dir, config.db_echo)

            job_db_path = sqlite_dir / "jobs.sqlite3"
            jobstores = {"default": SQLAlchemyJobStore(url=f"sqlite:///{job_db_path}")}
            scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=UTC)
            scheduler.start()
            job_scheduler = JobScheduler(scheduler)

            emailer = get_emailer(google_token_path)
            wait_deps = WaitlistDependencies(
                to_notify_db=wait_tn_db,
                notified_db=wait_an_db,
                job_scheduler=job_scheduler,
                emailer=emailer,
                password=pw,
            )
        else:
            wait_deps = None

        return cls(
            config=config,
            space_state_db=space_state_db,
            space_usage_db=space_usage_db,
            templates=Jinja2Templates(env=get_jinja_env()),
            sse_handler=SSEHandler(),
            wait_deps=wait_deps,
        )

    async def teardown(self) -> None:
        # Close SSE streams first so server shutdown isn't blocked by
        # long-lived event-stream connections.
        if self.sse_handler is not None:
            await self.sse_handler.shutdown()

        self.space_state_db.dispose()

        if self.config.waitlist:
            assert self.wait_deps is not None
            self.wait_deps.job_scheduler.shutdown(wait=False)
            self.wait_deps.to_notify_db.dispose()
            self.wait_deps.notified_db.dispose()


@dataclass(frozen=True)
class ScheduledJobContext:
    """context necessary for scheduled jobs pertaining to the waitlists, stored in
    apscheduler's sqlite jobstore. database connections, templates and email handler
    must be initialized per-job because they can't be pickled."""

    config: AppConfig
    sqlite_dir: DirectoryPath
    google_token_path: FilePath | None
