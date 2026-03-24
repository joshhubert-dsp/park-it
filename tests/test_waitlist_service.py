from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import cast

from fastapi.templating import Jinja2Templates
from jinja2 import Environment

from park_it.app.dependencies import (
    AppDependencies,
    ScheduledJobContext,
    WaitlistDependencies,
    get_jinja_env,
)
from park_it.models.app_config import AppConfig
from park_it.models.space import SpaceModel, SpaceState, SpaceType
from park_it.models.waitlist import WaitlistEntry
from park_it.services.db.database import (
    SPACE_STATE_DB_FILE_PREFIX,
    WAITLIST_NOTIFIED_DB_FILE_PREFIX,
    WAITLIST_TO_NOTIFY_DB_FILE_PREFIX,
    init_db,
)
from park_it.services.db.space_state_db import SpaceStateDatabase
from park_it.services.db.waitlist_db import WaitlistDatabase
from park_it.services.email.emailer import Emailer
from park_it.services.job_scheduler import JobScheduler
from park_it.services.waitlist_service import (
    cb_notify_next_entry_free,
    handle_waitlist_notification,
)
from tests.conftest import fake_app_config


@dataclass
class FakeJobScheduler:
    interval_runs: list[
        tuple[str, int, datetime, int, bool, object, dict[str, object]]
    ] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)

    def schedule_minutes_interval(
        self,
        job_id: str,
        minutes: int,
        start_dt: datetime,
        num_runs: int,
        first_no_wait: bool,
        callback: object,
        *,
        callback_kwargs: dict[str, object],
    ) -> None:
        self.interval_runs.append(
            (
                job_id,
                minutes,
                start_dt,
                num_runs,
                first_no_wait,
                callback,
                callback_kwargs,
            )
        )

    def cancel(self, job_id: str) -> None:
        self.cancelled.append(job_id)


@dataclass
class RecordingEmailer(Emailer):
    free_notifications: list[str] = field(default_factory=list)
    occupied_notifications: list[str] = field(default_factory=list)

    def send_join_confirmation(
        self, entry, waitlist_place, config, jinja_env: Environment
    ) -> bool:
        return True

    def send_leave_confirmation(self, entry, config, jinja_env: Environment) -> bool:
        return True

    def notify_free_space(self, entry, config, jinja_env: Environment) -> bool:
        self.free_notifications.append(entry.email)
        return True

    def notify_space_now_occupied(self, entry, config, jinja_env: Environment) -> bool:
        self.occupied_notifications.append(entry.email)
        return True


def _waitlist_entry(email: str) -> WaitlistEntry:
    return WaitlistEntry(
        email=email,
        space_type=SpaceType.STANDARD,
        timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
    )


def _get_wait_deps(deps: AppDependencies) -> WaitlistDependencies:
    assert deps.wait_deps is not None
    return deps.wait_deps


def _build_deps(
    tmp_path, config: AppConfig
) -> tuple[AppDependencies, FakeJobScheduler, ScheduledJobContext]:
    space_db: SpaceStateDatabase = init_db(
        tmp_path, SPACE_STATE_DB_FILE_PREFIX, SpaceStateDatabase, config.db_echo
    )
    wait_tn_db: WaitlistDatabase = init_db(
        tmp_path, WAITLIST_TO_NOTIFY_DB_FILE_PREFIX, WaitlistDatabase, config.db_echo
    )
    wait_an_db: WaitlistDatabase = init_db(
        tmp_path, WAITLIST_NOTIFIED_DB_FILE_PREFIX, WaitlistDatabase, config.db_echo
    )
    job_scheduler = FakeJobScheduler()

    for space in config.spaces:
        space_db.initial_insert(space.to_model())

    deps = AppDependencies(
        config=config,
        templates=Jinja2Templates(env=get_jinja_env()),
        space_state_db=space_db,
        space_usage_db=None,
        wait_deps=WaitlistDependencies(
            to_notify_db=wait_tn_db,
            notified_db=wait_an_db,
            emailer=RecordingEmailer(),
            job_scheduler=cast(JobScheduler, job_scheduler),
        ),
    )
    wait_deps = _get_wait_deps(deps)
    assert isinstance(wait_deps.emailer, RecordingEmailer)
    job_ctx = ScheduledJobContext(
        config=config,
        sqlite_dir=tmp_path,
        google_token_path=None,
    )
    return deps, job_scheduler, job_ctx


def test_handle_space_state_change_schedules_debounce_for_newly_free_space(tmp_path):
    config = fake_app_config(
        {"sensor_id": "sensor-1", "type": "standard", "label": "Spot 1"}
    )
    deps, job_scheduler, job_ctx = _build_deps(tmp_path, config)

    deps.space_state_db.upsert(
        SpaceModel(
            sensor_id="sensor-1",
            label="Spot 1",
            type=SpaceType.STANDARD,
            state=SpaceState.FREE,
            update_time=datetime(2026, 1, 1, 12, 1, 0, tzinfo=UTC),
        )
    )
    updated_space = deps.space_state_db.get("sensor-1")
    wait_deps = _get_wait_deps(deps)
    wait_deps.to_notify_db.insert(_waitlist_entry("first@example.com"))

    handle_waitlist_notification(
        updated_space=updated_space, deps=deps, job_ctx=job_ctx
    )

    assert len(job_scheduler.interval_runs) == 1
    assert job_scheduler.interval_runs[0][0] == "sensor-1"
    assert job_scheduler.interval_runs[0][1] == config.waitlist_interval_minutes
    assert job_scheduler.interval_runs[0][6] == {
        "sensor_id": "sensor-1",
        "job_ctx": job_ctx,
    }


def test_confirm_space_still_free_notifies_next_waiter(tmp_path, monkeypatch):
    config = fake_app_config(
        {"sensor_id": "sensor-1", "type": "standard", "label": "Spot 1"},
    )
    deps, job_scheduler, job_ctx = _build_deps(tmp_path, config)
    emailer = RecordingEmailer()

    deps.space_state_db.upsert(
        SpaceModel(
            sensor_id="sensor-1",
            label="Spot 1",
            type=SpaceType.STANDARD,
            state=SpaceState.FREE,
            update_time=datetime(2026, 1, 1, 12, 1, 0, tzinfo=UTC),
        )
    )
    wait_deps = _get_wait_deps(deps)
    wait_deps.to_notify_db.insert(_waitlist_entry("first@example.com"))

    monkeypatch.setattr(
        "park_it.services.waitlist_service.get_emailer", lambda f: emailer
    )
    asyncio.run(cb_notify_next_entry_free("sensor-1", job_ctx))

    assert emailer.free_notifications == ["first@example.com"]
    assert wait_deps.to_notify_db.count() == 0
    assert wait_deps.notified_db.count() == 1
    assert len(job_scheduler.interval_runs) == 0


def test_handle_space_state_change_notifies_when_last_free_space_becomes_occupied(
    tmp_path,
):
    config = fake_app_config(
        {"sensor_id": "sensor-1", "type": "standard", "label": "Spot 1"},
    )
    deps, job_scheduler, job_ctx = _build_deps(tmp_path, config)
    wait_deps = _get_wait_deps(deps)
    assert isinstance(wait_deps.emailer, RecordingEmailer)
    emailer = wait_deps.emailer

    deps.space_state_db.upsert(
        SpaceModel(
            sensor_id="sensor-1",
            label="Spot 1",
            type=SpaceType.STANDARD,
            state=SpaceState.FREE,
            update_time=datetime(2026, 1, 1, 12, 1, 0, tzinfo=UTC),
        )
    )
    wait_deps.notified_db.insert(_waitlist_entry("notified@example.com"))

    deps.space_state_db.upsert(
        SpaceModel(
            sensor_id="sensor-1",
            label="Spot 1",
            type=SpaceType.STANDARD,
            state=SpaceState.OCCUPIED,
            update_time=datetime(2026, 1, 1, 12, 2, 0, tzinfo=UTC),
        )
    )
    updated_space = deps.space_state_db.get("sensor-1")

    handle_waitlist_notification(
        updated_space=updated_space, deps=deps, job_ctx=job_ctx
    )

    assert job_scheduler.cancelled == ["sensor-1"]
    assert emailer.occupied_notifications == ["notified@example.com"]
    assert wait_deps.notified_db.count() == 0
    assert wait_deps.to_notify_db.count() == 0


def test_handle_space_state_change_does_not_flush_notified_waitlist_if_space_remains_free(
    tmp_path,
):
    config = fake_app_config(
        {"sensor_id": "sensor-1", "type": "standard", "label": "Spot 1"},
        {"sensor_id": "sensor-2", "type": "standard", "label": "Spot 2"},
    )
    deps, job_scheduler, job_ctx = _build_deps(tmp_path, config)
    wait_deps = _get_wait_deps(deps)
    assert isinstance(wait_deps.emailer, RecordingEmailer)
    emailer = wait_deps.emailer

    deps.space_state_db.upsert(
        SpaceModel(
            sensor_id="sensor-1",
            label="Spot 1",
            type=SpaceType.STANDARD,
            state=SpaceState.FREE,
            update_time=datetime(2026, 1, 1, 12, 1, 0, tzinfo=UTC),
        )
    )
    deps.space_state_db.upsert(
        SpaceModel(
            sensor_id="sensor-2",
            label="Spot 2",
            type=SpaceType.STANDARD,
            state=SpaceState.FREE,
            update_time=datetime(2026, 1, 1, 12, 1, 0, tzinfo=UTC),
        )
    )
    wait_deps.notified_db.insert(_waitlist_entry("notified@example.com"))

    deps.space_state_db.upsert(
        SpaceModel(
            sensor_id="sensor-1",
            label="Spot 1",
            type=SpaceType.STANDARD,
            state=SpaceState.OCCUPIED,
            update_time=datetime(2026, 1, 1, 12, 2, 0, tzinfo=UTC),
        )
    )
    updated_space = deps.space_state_db.get("sensor-1")

    handle_waitlist_notification(
        updated_space=updated_space, deps=deps, job_ctx=job_ctx
    )

    assert job_scheduler.cancelled == ["sensor-1"]
    assert emailer.occupied_notifications == []
    assert wait_deps.notified_db.count() == 1
