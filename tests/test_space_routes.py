from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.templating import Jinja2Templates
from sqlalchemy.engine.base import Engine

from park_it.app.dependencies import AppDependencies, get_jinja_env
from park_it.app.routes.space import (
    MedianSpaceUsageDuration,
    _build_space_state_context,
    _compute_space_usage,
)
from park_it.models.space import SpaceState, SpaceType, SpaceUsage
from park_it.services.db.database import create_session_factory
from park_it.services.db.space_state_db import SpaceStateDatabase
from park_it.services.db.space_usage_db import SpaceUsageDatabase
from tests.conftest import fake_app_config


@pytest.fixture
def space_state_db(sqlite_engine: Engine) -> SpaceStateDatabase:
    return SpaceStateDatabase(
        session_factory=create_session_factory(sqlite_engine),
        dispose_callback=sqlite_engine.dispose,
    )


@pytest.fixture
def space_usage_db(sqlite_engine: Engine) -> SpaceUsageDatabase:
    return SpaceUsageDatabase(
        session_factory=create_session_factory(sqlite_engine),
        dispose_callback=sqlite_engine.dispose,
    )


def _usage(
    *,
    sensor_id: str = "sensor-1",
    type: SpaceType = SpaceType.STANDARD,
    state: SpaceState,
    duration_sec: float,
) -> SpaceUsage:
    return SpaceUsage(  # pyright: ignore[reportCallIssue]
        sensor_id=sensor_id,
        type=type,
        state=state,
        update_time=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        duration_sec=duration_sec,
    )


def test_compute_space_usage_returns_none_without_history(
    space_usage_db: SpaceUsageDatabase,
):
    median_usage, wait_time = _compute_space_usage(
        SpaceType.STANDARD,
        space_usage_db,
        usage_median_num=10,
        num_spaces=2,
        wait_len=3,
    )

    assert median_usage is None
    assert wait_time is None


def test_compute_space_usage_returns_none_without_both_states(
    space_usage_db: SpaceUsageDatabase,
):
    space_usage_db.insert(
        _usage(state=SpaceState.OCCUPIED, duration_sec=300.0),
    )

    median_usage, wait_time = _compute_space_usage(
        SpaceType.STANDARD,
        space_usage_db,
        usage_median_num=10,
        num_spaces=2,
        wait_len=3,
    )

    assert median_usage is None
    assert wait_time is None


def test_compute_space_usage_returns_medians_and_wait_time(
    space_usage_db: SpaceUsageDatabase,
):
    for row in [
        _usage(state=SpaceState.OCCUPIED, duration_sec=300.0),
        _usage(state=SpaceState.OCCUPIED, duration_sec=900.0),
        _usage(state=SpaceState.OCCUPIED, duration_sec=1200.0),
        _usage(state=SpaceState.FREE, duration_sec=60.0),
        _usage(state=SpaceState.FREE, duration_sec=120.0),
        _usage(state=SpaceState.FREE, duration_sec=180.0),
    ]:
        space_usage_db.insert(row)

    median_usage, wait_time = _compute_space_usage(
        SpaceType.STANDARD,
        space_usage_db,
        usage_median_num=10,
        num_spaces=3,
        wait_len=2,
    )

    assert median_usage == MedianSpaceUsageDuration(900.0, 120.0)
    assert wait_time == 680.0


def test_build_space_state_context_omits_usage_estimates_without_complete_history(
    space_state_db: SpaceStateDatabase,
    space_usage_db: SpaceUsageDatabase,
):
    config = fake_app_config(
        {"sensor_id": "sensor-1", "type": "standard", "label": "Spot 1"}
    )
    for space in config.spaces:
        space_state_db.initial_insert(space.to_model())

    space_usage_db.insert(
        _usage(state=SpaceState.OCCUPIED, duration_sec=300.0),
    )

    deps = AppDependencies(
        config=config,
        templates=Jinja2Templates(env=get_jinja_env()),
        space_state_db=space_state_db,
        space_usage_db=space_usage_db,
        sse_handler=None,
        wait_deps=None,
    )

    context = _build_space_state_context(deps)

    assert context["free_spaces"] == {SpaceType.STANDARD: 0}
    assert context["median_usage"] == {}
    assert context["wait_times"] == {}
