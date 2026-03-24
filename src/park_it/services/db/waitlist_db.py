from sqlalchemy import Select, delete, func
from sqlmodel import select

from park_it.models.space import SpaceType
from park_it.models.waitlist import WaitlistEntry
from park_it.services.db.database import Database


class JoinedListAlready(Exception):
    pass


class WaitlistDatabase(Database):
    """Data access wrapper around the WaitlistEntry SQLModel. Used for both initial
    waitlist and list of people who have already been emailed to notify them when a
    space is occupied again"""

    table_models = (WaitlistEntry,)

    def joined_already(self, entry: WaitlistEntry) -> bool:
        with self._session_factory() as session:
            stmt = select(WaitlistEntry).where(WaitlistEntry.email == entry.email)
            return session.exec(stmt).one_or_none() is not None

    def insert(self, entry: WaitlistEntry) -> WaitlistEntry:
        """will only add the entry object if it isn't already present"""
        if self.joined_already(entry):
            raise JoinedListAlready

        with self._session_factory() as session:
            session.add(entry)
            session.commit()
            # session.refresh(entry)

        return entry

    def pop(self, type: SpaceType | None = None) -> WaitlistEntry | None:
        with self._session_factory() as session:
            # Subquery selects the id of the row we want to pop
            subq: Select = select(WaitlistEntry.id)
            if type is not None:
                subq = subq.where(WaitlistEntry.space_type == type)

            subq = subq.order_by(WaitlistEntry.id).limit(1)  # pyright: ignore[reportArgumentType]

            # Atomic: delete the selected row and return it
            stmt = (
                delete(WaitlistEntry)
                .where(WaitlistEntry.id == subq.scalar_subquery())  # pyright: ignore[reportArgumentType]
                .returning(WaitlistEntry)
            )
            row = session.exec(stmt).one_or_none()
            session.commit()
            return row[0] if row is not None else None

    def count(self, type: SpaceType | None = None) -> int:
        with self._session_factory() as session:
            stmt = select(func.count()).select_from(WaitlistEntry)
            if type is not None:
                stmt = stmt.where(WaitlistEntry.space_type == type)
            return session.exec(stmt).one()

    def delete(self, email: str) -> bool:
        """returns True if something was found to be deleted"""
        with self._session_factory() as session:
            # fmt: off
            stmt = delete(WaitlistEntry).where(WaitlistEntry.email == email).returning(WaitlistEntry.id) # pyright: ignore[reportCallIssue, reportArgumentType]
            # fmt: on
            row = session.exec(stmt).one_or_none()
            session.commit()
            return row is not None
