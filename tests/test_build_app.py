from __future__ import annotations

import asyncio

from park_it.app.build_app import build_app
from park_it.models.space_update import DummySpaceUpdate
from park_it.services.email.emailer import PrintDebugEmailer
from tests.conftest import fake_app_config

SPACES = {
    "sensor_id": "sensor-1",
    "type": "standard",
    "label": "Spot 1",
}


def test_build_app_uses_concrete_space_update_model_in_openapi(tmp_path):
    sqlite_dir = tmp_path / "sqlite"
    sqlite_dir.mkdir()
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "index.html").write_text("ok", encoding="utf-8")

    app = build_app(
        DummySpaceUpdate,
        app_config=fake_app_config(SPACES),
        sqlite_dir=sqlite_dir,
        site_dir=site_dir,
    )

    schema = app.openapi()
    request_schema = schema["paths"]["/space/update-state"]["post"]["requestBody"][
        "content"
    ]["application/json"]["schema"]

    assert request_schema == {"$ref": "#/components/schemas/DummySpaceUpdate"}


def test_build_app_validates_update_state_with_concrete_space_update_model(tmp_path):
    sqlite_dir = tmp_path / "sqlite"
    sqlite_dir.mkdir()
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "index.html").write_text("ok", encoding="utf-8")

    app = build_app(
        DummySpaceUpdate,
        app_config=fake_app_config(SPACES),
        sqlite_dir=sqlite_dir,
        site_dir=site_dir,
    )
    route = next(
        route
        for route in app.routes
        if getattr(route, "path", None) == "/space/update-state"
    )
    body_field = route.body_field  # pyright: ignore[reportAttributeAccessIssue]

    value, errors = body_field.validate(
        {
            "id": "sensor-1",
            "dt": "2026-01-01T12:00:00Z",
        },
        {},
        loc=("body",),
    )

    assert body_field.field_info.annotation is DummySpaceUpdate
    assert value is None
    assert errors == [
        {
            "type": "missing",
            "loc": ("body", "occ"),
            "msg": "Field required",
            "input": {
                "id": "sensor-1",
                "dt": "2026-01-01T12:00:00Z",
            },
        }
    ]


def test_build_app_uses_print_debug_emailer(tmp_path):
    sqlite_dir = tmp_path / "sqlite"
    sqlite_dir.mkdir()
    site_dir = tmp_path / "site"
    site_dir.mkdir()
    (site_dir / "index.html").write_text("ok", encoding="utf-8")

    app = build_app(
        DummySpaceUpdate,
        app_config=fake_app_config(SPACES),
        sqlite_dir=sqlite_dir,
        site_dir=site_dir,
        google_token_path=None,
    )

    async def run_lifespan():
        async with app.router.lifespan_context(app):
            assert app.state.deps.wait_deps is not None
            assert isinstance(app.state.deps.wait_deps.emailer, PrintDebugEmailer)

    asyncio.run(run_lifespan())
