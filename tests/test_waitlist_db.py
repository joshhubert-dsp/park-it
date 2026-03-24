import os
from typing import cast

import pytest

from park_it.models.space import SpaceType
from park_it.models.waitlist import WaitlistRequest
from park_it.services.db.database import create_session_factory
from park_it.services.db.waitlist_db import JoinedListAlready, WaitlistDatabase


@pytest.fixture
def waitlist_db(sqlite_engine):
    return WaitlistDatabase(
        session_factory=create_session_factory(sqlite_engine),
        dispose_callback=sqlite_engine.dispose,
    )


def _waitlist_request(email: str) -> WaitlistRequest:
    return WaitlistRequest(
        password=cast(str, os.getenv("PARK_IT_WAITLIST_PASSWORD")),
        email=email,
        space_type=SpaceType.EV_CHARGER,
    )
    # timestamp=timestamp or datetime(2026, 1, 1, 12, 0, 0),


def test_waitlist_insert(waitlist_db: WaitlistDatabase):
    entry = _waitlist_request("first@example.com").to_entry()
    assert waitlist_db.joined_already(entry) is False

    inserted = waitlist_db.insert(entry)
    assert inserted.email == "first@example.com"
    assert waitlist_db.joined_already(entry) is True
    assert waitlist_db.count() == 1


def test_waitlist_pop(waitlist_db: WaitlistDatabase):
    entry = _waitlist_request("first@example.com").to_entry()
    assert waitlist_db.joined_already(entry) is False

    waitlist_db.insert(entry)
    popped = waitlist_db.pop()
    assert popped is not None
    assert popped.email == "first@example.com"
    assert waitlist_db.joined_already(entry) is False
    assert waitlist_db.count() == 0


def test_waitlist_insert_duplicate_email_raises(waitlist_db: WaitlistDatabase):
    waitlist_db.insert(_waitlist_request("dupe@example.com").to_entry())

    with pytest.raises(JoinedListAlready):
        waitlist_db.insert(_waitlist_request("dupe@example.com").to_entry())
    assert waitlist_db.count() == 1


def test_waitlist_delete_removes_entry(waitlist_db: WaitlistDatabase):
    waitlist_db.insert(_waitlist_request("delete-me@example.com").to_entry())
    waitlist_db.insert(_waitlist_request("keep-me@example.com").to_entry())
    assert waitlist_db.count() == 2

    assert waitlist_db.delete("delete-me@example.com")
    assert waitlist_db.count() == 1
    assert (
        waitlist_db.joined_already(
            _waitlist_request("delete-me@example.com").to_entry()
        )
        is False
    )
