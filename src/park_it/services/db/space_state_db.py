from loguru import logger
from sqlalchemy import delete, func
from sqlmodel import select

from park_it.models.space import SpaceModel, SpaceState, SpaceType
from park_it.services.db.database import Database


class SpaceStateDatabase(Database):
    """Data access wrapper around the Space SQLModel."""

    table_models = (SpaceModel,)

    @staticmethod
    def _validated_space_required(space: SpaceModel | None) -> SpaceModel:
        """necessary to ensure datetimes are converted to UTC (SQLite/sqlalchemy doesn't handle that)"""
        if space is None:
            raise LookupError
        return SpaceModel.model_validate(space.model_dump())

    def initial_insert(self, entry: SpaceModel) -> SpaceModel:
        """initial insert from config. will add add a new space object if sensor_id is new.
        otherwise will update the type, label, and OUT_OF_ORDER state of an existing space."""
        with self._session_factory() as session:
            prev = session.get(SpaceModel, entry.sensor_id)
            if prev is None:
                session.add(entry)
            else:
                prev.type = entry.type
                prev.label = entry.label
                # out of order from config overrides any previous state, and existing
                # out of order db model should be overridden upon hardware fix
                if (
                    entry.state == SpaceState.OUT_OF_ORDER
                    or prev.state == SpaceState.OUT_OF_ORDER
                ):
                    prev.state = entry.state
                session.add(prev)
                entry = prev

            session.commit()
            session.refresh(entry)

            return self._validated_space_required(entry)

    def upsert(self, entry: SpaceModel) -> SpaceModel:
        """Apply a runtime state update to an already initialized space row."""
        with self._session_factory() as session:
            curr = session.get(SpaceModel, entry.sensor_id)
            if curr is None:
                raise LookupError(
                    f"Sensor '{entry.sensor_id}' is not initialized. "
                    "Call initial_insert(config) first."
                )
            elif curr.state is SpaceState.OUT_OF_ORDER:
                logger.debug(
                    f"UPDATE message ignored for OUT-OF-ORDER sensor: {curr.sensor_id}"
                )
                return curr

            curr.state = entry.state
            curr.update_time = entry.update_time
            session.add(curr)
            session.commit()
            session.refresh(curr)

        return self._validated_space_required(curr)

    def get(self, sensor_id: str) -> SpaceModel:
        with self._session_factory() as session:
            stmt = select(SpaceModel).where(SpaceModel.sensor_id == sensor_id)
            return self._validated_space_required(session.exec(stmt).one_or_none())

    def count(self, type: SpaceType | None = None, only_free: bool = False):
        with self._session_factory() as session:
            stmt = select(func.count()).select_from(SpaceModel)
            if type is not None:
                stmt = stmt.where(SpaceModel.type == type)
            if only_free:
                stmt = stmt.where(SpaceModel.state == SpaceState.FREE)
            return session.exec(stmt).one()

    def delete(self, sensor_id: str) -> bool:
        """returns True if something was found to be deleted"""
        with self._session_factory() as session:
            # fmt: off
            stmt = delete(SpaceModel).where(SpaceModel.sensor_id == sensor_id).returning(SpaceModel.sensor_id) # pyright: ignore[reportCallIssue, reportArgumentType]
            # fmt: on
            row = session.exec(stmt).one_or_none()
            session.commit()
            return row is not None
