from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.engine.base import Engine
from sqlmodel import SQLModel, create_engine

from park_it.models.app_config import AppConfig


@pytest.fixture
def sqlite_engine(tmp_path: Path) -> Generator[Engine, Any, None]:
    db_path = tmp_path / "test.sqlite3"
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


def fake_app_config(*spaces: dict[str, str]) -> AppConfig:
    return AppConfig.model_validate(
        {
            "title": "Park It",
            "description": "test app",
            "version": "0.1.0",
            "app_email": "parking@example.com",
            "app_email_name": "Peter Parker",
            "app_url": "http://parkingexample.com",
            "spaces": list(spaces),
        }
    )
