from pydantic import AwareDatetime
from sqlalchemy import delete, func
from sqlmodel import desc, select

from park_it.models.space import SpaceState, SpaceType, SpaceUsage
from park_it.services.db.database import Database


# TODO tests
class SpaceUsageDatabase(Database):
    """Data access wrapper around the SpaceUsage SQLModel. Since these entries represent
    durations of occupied/free time, each one is necessarily unique and all that's
    required is inserting/getting/counting"""

    table_models = (SpaceUsage,)

    def insert(self, entry: SpaceUsage) -> SpaceUsage:
        with self._session_factory() as session:
            session.add(entry)
            session.commit()
            session.refresh(entry)
            return entry

    def get(
        self,
        n_newest: int | None = None,
        sensor_id: str | None = None,
        state: SpaceState | None = None,
        type: SpaceType | None = None,
        start_dt: AwareDatetime | None = None,
        end_dt: AwareDatetime | None = None,
    ) -> list[SpaceUsage]:
        with self._session_factory() as session:
            stmt = select(SpaceUsage)
            if n_newest is not None:
                stmt = stmt.order_by(desc(SpaceUsage.id)).limit(n_newest)
            if sensor_id is not None:
                stmt = stmt.where(SpaceUsage.sensor_id == sensor_id)
            if state is not None:
                stmt = stmt.where(SpaceUsage.state == state)
            if type is not None:
                stmt = stmt.where(SpaceUsage.type == type)
            if start_dt is not None:
                stmt = stmt.where(SpaceUsage.update_time >= start_dt)
            if end_dt is not None:
                stmt = stmt.where(SpaceUsage.update_time < end_dt)
            return list(session.exec(stmt))

    def count(
        self,
        sensor_id: str | None = None,
        state: SpaceState | None = None,
        type: SpaceType | None = None,
        start_dt: AwareDatetime | None = None,
        end_dt: AwareDatetime | None = None,
    ):
        with self._session_factory() as session:
            stmt = select(func.count()).select_from(SpaceUsage)
            if sensor_id is not None:
                stmt = stmt.where(SpaceUsage.sensor_id == sensor_id)
            if state is not None:
                stmt = stmt.where(SpaceUsage.state == state)
            if type is not None:
                stmt = stmt.where(SpaceUsage.type == type)
            if start_dt is not None:
                stmt = stmt.where(SpaceUsage.update_time >= start_dt)
            if end_dt is not None:
                stmt = stmt.where(SpaceUsage.update_time < end_dt)
            return session.exec(stmt).one()

    def delete(self, sensor_id: str) -> bool:
        """returns True if something was found to be deleted"""
        with self._session_factory() as session:
            # fmt: off
            stmt = delete(SpaceUsage).where(SpaceUsage.sensor_id == sensor_id).returning(SpaceUsage.sensor_id) # pyright: ignore[reportCallIssue, reportArgumentType]
            # fmt: on
            deleted = session.exec(stmt).first()
            session.commit()
            return deleted is not None
