from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.engine.base import Engine

from park_it.models.space import (
    SpaceConfig,
    SpaceModel,
    SpaceState,
    SpaceType,
)
from park_it.models.space_update import DummySpaceUpdate
from park_it.services.db.database import (
    create_session_factory,
)
from park_it.services.db.space_state_db import SpaceStateDatabase


@pytest.fixture
def space_state_db(sqlite_engine: Engine):
    return SpaceStateDatabase(
        session_factory=create_session_factory(sqlite_engine),
        dispose_callback=sqlite_engine.dispose,
    )


def _space_config(sensor_id: str, type: SpaceType = SpaceType.STANDARD) -> SpaceConfig:
    return SpaceConfig(sensor_id=sensor_id, type=type, label="test")


def _space_update(
    sensor_id: str, occupied: bool = True, last_update: datetime | None = None
) -> DummySpaceUpdate:
    return DummySpaceUpdate(
        id=sensor_id,
        occ=occupied,
        dt=last_update or datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
    )


def _space_model(
    sensor_id: str,
    state: SpaceState = SpaceState.OCCUPIED,
    last_update: datetime | None = None,
) -> SpaceModel:
    return SpaceModel(
        sensor_id=sensor_id,
        type=SpaceType.STANDARD,
        label="test",
        state=state,
        update_time=last_update or datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
    )


def test_space_initial_insert_and_delete(space_state_db: SpaceStateDatabase):
    inserted = space_state_db.initial_insert(_space_config("sensor-1").to_model())
    assert inserted is not None
    persisted = space_state_db.get("sensor-1")
    assert persisted is not None
    assert persisted.state is SpaceState.OCCUPIED
    assert space_state_db.count() == 1

    assert space_state_db.delete("sensor-1")

    with pytest.raises(LookupError):
        space_state_db.get("sensor-1")
        # assert space_db.get("sensor-1") is None
    assert space_state_db.count() == 0


def test_space_upsert_updates_existing_row(space_state_db: SpaceStateDatabase):
    baseline_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    updated_time = baseline_time + timedelta(minutes=5)
    space_state_db.initial_insert(_space_config("sensor-1").to_model())

    updated = space_state_db.upsert(
        _space_model("sensor-1", SpaceState.OCCUPIED, last_update=updated_time)
    )
    assert updated is not None
    persisted = space_state_db.get("sensor-1")
    assert persisted is not None
    assert persisted.state is SpaceState.OCCUPIED
    assert persisted.update_time == updated_time
    assert space_state_db.count(SpaceType.STANDARD) == 1
    assert space_state_db.count(SpaceType.STANDARD, only_free=True) == 0


def test_space_get_normalizes_update_time_to_utc(space_state_db: SpaceStateDatabase):
    update_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    space_state_db.initial_insert(
        _space_model("sensor-1", SpaceState.OCCUPIED, last_update=update_time)
    )

    persisted = space_state_db.get("sensor-1")

    assert persisted is not None
    assert persisted.update_time == update_time
    assert persisted.update_time.tzinfo == UTC


@pytest.mark.parametrize(
    ("space_type", "only_free", "expected"),
    [
        pytest.param(SpaceType.STANDARD, False, 3, id="standard-total"),
        pytest.param(SpaceType.STANDARD, True, 2, id="standard-free"),
        pytest.param(SpaceType.EV_CHARGER, False, 1, id="ev-total"),
        pytest.param(SpaceType.EV_CHARGER, True, 0, id="ev-free"),
    ],
)
def test_space_count_filters_by_type_and_occupancy(
    space_state_db: SpaceStateDatabase,
    space_type: SpaceType,
    only_free: bool,
    expected: int,
):
    for space in [
        _space_config("s1", type=SpaceType.STANDARD),
        _space_config("s2", type=SpaceType.STANDARD),
        _space_config("s3", type=SpaceType.STANDARD),
        _space_config("s4", type=SpaceType.EV_CHARGER),
    ]:
        space_state_db.initial_insert(space.to_model())
    for space in [
        _space_update("s1", occupied=True),
        _space_update("s2", occupied=False),
        _space_update("s3", occupied=False),
        _space_update("s4", occupied=True),
    ]:
        space_state_db.upsert(space.to_model())

    assert space_state_db.count(space_type, only_free=only_free) == expected
