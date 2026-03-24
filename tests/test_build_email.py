from __future__ import annotations

from datetime import UTC, datetime

from park_it.app.dependencies import get_jinja_env
from park_it.models.space import SpaceType
from park_it.models.waitlist import WaitlistEntry
from park_it.services.email.build_email import (
    build_join_confirm_email,
    build_leave_confirm_email,
    build_space_free_email,
    build_space_occupied_email,
)
from tests.conftest import fake_app_config


def _entry(email: str = "first@example.com") -> WaitlistEntry:
    return WaitlistEntry(
        email=email,
        space_type=SpaceType.EV_CHARGER,
        timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
    )


def test_build_join_confirm_email():
    config = fake_app_config(
        {"sensor_id": "s1", "type": "standard", "label": "Spot 1"},
    )
    jinja_env = get_jinja_env()
    entry = _entry()

    msg = build_join_confirm_email(
        entry, waitlist_place=2, config=config, jinja_env=jinja_env
    )

    assert msg["To"] == entry.email
    assert msg["From"] == f"{config.app_email_name} <{config.app_email}>"
    assert msg["Subject"] == f"You Joined the {entry.space_type.upper()} Space Waitlist"
    assert msg.get_content_type() == "multipart/alternative"

    plain = msg.get_body(preferencelist=("plain",))
    html = msg.get_body(preferencelist=("html",))

    assert plain is not None
    assert html is not None
    assert "2nd" in plain.get_content()
    assert str(config.waitlist_interval_minutes) in plain.get_content()
    assert "2nd" in html.get_content()


def test_build_leave_confirm_email():
    config = fake_app_config(
        {"sensor_id": "s1", "type": "standard", "label": "Spot 1"},
    )
    jinja_env = get_jinja_env()
    entry = _entry()

    msg = build_leave_confirm_email(entry, config=config, jinja_env=jinja_env)

    assert msg["To"] == entry.email
    assert msg["From"] == f"{config.app_email_name} <{config.app_email}>"
    assert msg["Subject"] == "You Left the Space Waitlist"

    plain = msg.get_body(preferencelist=("plain",))
    html = msg.get_body(preferencelist=("html",))

    assert plain is not None
    assert html is not None
    assert "thanks you for leaving" in plain.get_content().lower()
    assert "thanks you for leaving" in html.get_content().lower()


def test_build_space_free_email():
    config = fake_app_config(
        {"sensor_id": "s1", "type": "standard", "label": "Spot 1"},
    )
    jinja_env = get_jinja_env()
    entry = _entry()

    msg = build_space_free_email(entry, config=config, jinja_env=jinja_env)

    assert msg["To"] == entry.email
    assert msg["From"] == f"{config.app_email_name} <{config.app_email}>"
    assert msg["Subject"] == f"{entry.space_type.upper()} Space is Available!"

    plain = msg.get_body(preferencelist=("plain",))
    html = msg.get_body(preferencelist=("html",))

    assert plain is not None
    assert html is not None
    assert "made it off the waitlist" in plain.get_content().lower()
    assert "made it off the waitlist" in html.get_content().lower()


def test_build_space_occupied_email():
    config = fake_app_config(
        {"sensor_id": "s1", "type": "standard", "label": "Spot 1"},
    )
    jinja_env = get_jinja_env()
    entry = _entry()

    msg = build_space_occupied_email(entry, config=config, jinja_env=jinja_env)

    assert msg["To"] == entry.email
    assert msg["From"] == f"{config.app_email_name} <{config.app_email}>"
    assert msg["Subject"] == f"{entry.space_type.upper()} Space No Longer Available"

    plain = msg.get_body(preferencelist=("plain",))
    html = msg.get_body(preferencelist=("html",))

    assert plain is not None
    assert html is not None
    assert "all spaces of that type are now occupied" in plain.get_content().lower()
    assert "all spaces of that type are now occupied" in html.get_content().lower()
