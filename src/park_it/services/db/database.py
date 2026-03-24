from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager, contextmanager
from typing import ClassVar, TypeVar

from pydantic import DirectoryPath
from sqlalchemy import Engine as SqlEngine
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

SessionFactory = Callable[[], AbstractContextManager[Session]]
TableModel = type[SQLModel]

SPACE_STATE_DB_FILE_PREFIX = "space-state"
SPACE_USAGE_DB_FILE_PREFIX = "space-usage"
WAITLIST_TO_NOTIFY_DB_FILE_PREFIX = "waitlist-to-notify"
WAITLIST_NOTIFIED_DB_FILE_PREFIX = "waitlist-notified"


def create_db_engine(
    sqlite_db_path: DirectoryPath,
    file_prefix: str,
    table_models: tuple[TableModel, ...],
    db_echo: bool = False,
) -> SqlEngine:
    sqlite_db_path.mkdir(parents=True, exist_ok=True)
    db_filepath = sqlite_db_path / f"{file_prefix}.sqlite3"
    sqlite_url = f"sqlite:///{db_filepath}"
    engine = create_engine(
        sqlite_url,
        echo=db_echo,
        connect_args={"check_same_thread": False},  # allow usage across threads
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        # Enables Write-Ahead Logging: readers don’t block writers
        cursor.execute("PRAGMA journal_mode=WAL;")
        # Slightly less durable than FULL, much faster
        cursor.execute("PRAGMA synchronous=NORMAL;")
        # On write contention, SQLite waits up to 5 seconds, instead of instantly
        # erroring with "database is locked"
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.close()

    tables = [
        getattr(model, "__table__")  # noqa: B009 for SQLModel type-checking weirdness
        for model in table_models
    ]
    SQLModel.metadata.create_all(engine, tables=tables)
    return engine


def create_session_factory(engine: SqlEngine, expire_on_commit=False) -> SessionFactory:
    """Create a session factory bound to the provided engine."""

    @contextmanager
    def session_scope():
        with Session(engine, expire_on_commit=expire_on_commit) as session:
            yield session

    return session_scope


class Database:
    table_models: ClassVar[tuple[TableModel, ...]] = ()

    def __init__(
        self,
        session_factory: SessionFactory,
        dispose_callback: Callable[[], None],
    ) -> None:
        self._session_factory = session_factory
        self._dispose_callback = dispose_callback

    def dispose(self) -> None:
        self._dispose_callback()


T = TypeVar("T", bound=Database)


def init_db(
    sqlite_dir: DirectoryPath,
    file_prefix: str,
    db_class: type[T],
    # db_class: type[SpaceSQLiteDatabase | WaitlistDatabase],
    db_echo: bool = False,
) -> T:
    if not db_class.table_models:
        raise ValueError(f"{db_class.__name__} must define table_models")

    engine = create_db_engine(sqlite_dir, file_prefix, db_class.table_models, db_echo)
    session_factory = create_session_factory(engine)
    db = db_class(session_factory, engine.dispose)
    return db
