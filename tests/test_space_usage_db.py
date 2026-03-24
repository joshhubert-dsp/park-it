from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.engine.base import Engine

from park_it.models.space import SpaceState, SpaceType, SpaceUsage
from park_it.services.db.database import create_session_factory
from park_it.services.db.space_usage_db import SpaceUsageDatabase


@pytest.fixture
def space_usage_db(sqlite_engine: Engine) -> SpaceUsageDatabase:
    return SpaceUsageDatabase(
        session_factory=create_session_factory(sqlite_engine),
        dispose_callback=sqlite_engine.dispose,
    )


def _usage(
    sensor_id: str,
    *,
    type: SpaceType = SpaceType.STANDARD,
    state: SpaceState = SpaceState.OCCUPIED,
    update_time: datetime | None = None,
    duration_sec: float = 300.0,
) -> SpaceUsage:
    return SpaceUsage(  # pyright: ignore[reportCallIssue]
        sensor_id=sensor_id,
        type=type,
        state=state,
        update_time=update_time or datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        duration_sec=duration_sec,
    )


def _seed_usage_rows(space_usage_db: SpaceUsageDatabase) -> list[SpaceUsage]:
    base_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    rows = [
        _usage(
            "sensor-a",
            state=SpaceState.OCCUPIED,
            update_time=base_time,
            duration_sec=120.0,
        ),
        _usage(
            "sensor-b",
            type=SpaceType.EV_CHARGER,
            state=SpaceState.FREE,
            update_time=base_time + timedelta(minutes=5),
            duration_sec=240.0,
        ),
        _usage(
            "sensor-a",
            type=SpaceType.EV_CHARGER,
            state=SpaceState.FREE,
            update_time=base_time + timedelta(minutes=10),
            duration_sec=360.0,
        ),
        _usage(
            "sensor-c",
            state=SpaceState.OUT_OF_ORDER,
            update_time=base_time + timedelta(minutes=15),
            duration_sec=480.0,
        ),
    ]
    return [space_usage_db.insert(row) for row in rows]


def test_space_usage_insert_persists_row(space_usage_db: SpaceUsageDatabase):
    entry = _usage("sensor-1")

    inserted = space_usage_db.insert(entry)

    assert inserted.id is not None
    persisted = space_usage_db.get(sensor_id="sensor-1")
    assert len(persisted) == 1
    assert persisted[0].id == inserted.id
    assert persisted[0].duration_sec == 300.0
    assert space_usage_db.count() == 1


def test_space_usage_get_returns_n_newest_rows_in_descending_id_order(
    space_usage_db: SpaceUsageDatabase,
):
    inserted = _seed_usage_rows(space_usage_db)

    newest_two = space_usage_db.get(n_newest=2)

    assert [row.id for row in newest_two] == [inserted[3].id, inserted[2].id]


@pytest.mark.parametrize(
    ("filters", "expected_sensor_ids"),
    [
        pytest.param({"sensor_id": "sensor-a"}, ["sensor-a", "sensor-a"], id="sensor"),
        pytest.param({"state": SpaceState.FREE}, ["sensor-b", "sensor-a"], id="state"),
        pytest.param(
            {"type": SpaceType.EV_CHARGER}, ["sensor-b", "sensor-a"], id="type"
        ),
        pytest.param(
            {"start_dt": datetime(2026, 1, 1, 12, 5, 0, tzinfo=UTC)},
            ["sensor-b", "sensor-a", "sensor-c"],
            id="start-inclusive",
        ),
        pytest.param(
            {"end_dt": datetime(2026, 1, 1, 12, 10, 0, tzinfo=UTC)},
            ["sensor-a", "sensor-b"],
            id="end-exclusive",
        ),
        pytest.param(
            {
                "sensor_id": "sensor-a",
                "state": SpaceState.FREE,
                "type": SpaceType.EV_CHARGER,
                "start_dt": datetime(2026, 1, 1, 12, 10, 0, tzinfo=UTC),
                "end_dt": datetime(2026, 1, 1, 12, 15, 0, tzinfo=UTC),
            },
            ["sensor-a"],
            id="combined",
        ),
    ],
)
def test_space_usage_get_applies_filters(
    space_usage_db: SpaceUsageDatabase,
    filters: dict[str, object],
    expected_sensor_ids: list[str],
):
    _seed_usage_rows(space_usage_db)
    rows = space_usage_db.get(**filters)  # pyright: ignore[reportArgumentType]
    assert [row.sensor_id for row in rows] == expected_sensor_ids


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        pytest.param({}, 4, id="all"),
        pytest.param({"sensor_id": "sensor-a"}, 2, id="sensor"),
        pytest.param({"state": SpaceState.FREE}, 2, id="state"),
        pytest.param({"type": SpaceType.EV_CHARGER}, 2, id="type"),
        pytest.param(
            {"start_dt": datetime(2026, 1, 1, 12, 5, 0, tzinfo=UTC)},
            3,
            id="start-inclusive",
        ),
        pytest.param(
            {"end_dt": datetime(2026, 1, 1, 12, 10, 0, tzinfo=UTC)},
            2,
            id="end-exclusive",
        ),
        pytest.param(
            {
                "sensor_id": "sensor-a",
                "state": SpaceState.FREE,
                "type": SpaceType.EV_CHARGER,
                "start_dt": datetime(2026, 1, 1, 12, 10, 0, tzinfo=UTC),
                "end_dt": datetime(2026, 1, 1, 12, 15, 0, tzinfo=UTC),
            },
            1,
            id="combined",
        ),
    ],
)
def test_space_usage_count_applies_filters(
    space_usage_db: SpaceUsageDatabase,
    filters: dict[str, object],
    expected: int,
):
    _seed_usage_rows(space_usage_db)

    assert space_usage_db.count(**filters) == expected  # pyright: ignore[reportArgumentType]


def test_space_usage_delete_removes_all_rows_for_sensor(
    space_usage_db: SpaceUsageDatabase,
):
    _seed_usage_rows(space_usage_db)

    deleted = space_usage_db.delete("sensor-a")

    assert deleted is True
    assert space_usage_db.count() == 2
    assert space_usage_db.count(sensor_id="sensor-a") == 0
    assert [row.sensor_id for row in space_usage_db.get()] == ["sensor-b", "sensor-c"]


def test_space_usage_delete_returns_false_when_sensor_missing(
    space_usage_db: SpaceUsageDatabase,
):
    _seed_usage_rows(space_usage_db)

    deleted = space_usage_db.delete("missing-sensor")

    assert deleted is False
    assert space_usage_db.count() == 4
