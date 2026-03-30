import os
from functools import partial
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI
from fastapi.concurrency import asynccontextmanager
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import ConfigDict, DirectoryPath, FilePath, ValidationError, validate_call

from park_it.app.dependencies import (
    AppDependencies,
    ScheduledJobContext,
)
from park_it.app.routes.space import create_space_router
from park_it.app.routes.waitlist_form import waitlist_form_router
from park_it.app.utils import (
    handle_validation_error,
    log_request_validation_error,
    log_unexpected_exception,
)
from park_it.models.app_config import AppConfig
from park_it.models.field_types import YamlPath
from park_it.models.space_update import SpaceUpdateBaseModel

# TODO maybe checkbox to switch "spaces occupied again" email

DEFAULT_APP_CONFIG_FILE = "app-config.yaml"
DEFAULT_SQLITE_DIR = "sqlite-dbs"
DEFAULT_GOOGLE_TOKEN_FILE = "auth-token.json"
DEFAULT_SITE_DIR = "site"


class _Default:
    __slots__ = ()

    def __repr__(self) -> str:
        return "DEFAULT ARGUMENT"


DEFAULT = _Default()


@validate_call(config=ConfigDict(arbitrary_types_allowed=True))
def build_app(
    space_update_model: type[SpaceUpdateBaseModel],
    app_config: AppConfig | YamlPath | _Default = DEFAULT,
    sqlite_dir: DirectoryPath | _Default = DEFAULT,
    site_dir: DirectoryPath | _Default = DEFAULT,
    google_token_path: FilePath | None | _Default = DEFAULT,
    waitlist_password_path: FilePath | None = None,
) -> FastAPI:
    """Build a configured parking status FastAPI application.

    The returned app loads its runtime dependencies during lifespan startup, registers
    the space-status and waitlist routes, and serves the built static site from the
    configured `site_dir`.

    Args:
        space_update_model (type[SpaceUpdateBaseModel]): Concrete Pydantic payload model
            used to validate parking sensor updates posted to the endpoint `/space/update-state`.
        app_config (AppConfig | YamlPath, optional): Either an `AppConfig` instance or a YAML path
            to load one from. Defaults to `[CWD]/app-config.yaml`.
        sqlite_dir (DirectoryPath, optional): Directory where the app stores its SQLite databases. Defaults to
            `[CWD]/sqlite-dbs/`.
        site_dir (DirectoryPath, optional): Directory containing the built static site
            to mount at `/`. If a non-default path is desired, it's recommended to not
            pass this argument and instead set the environment variable
            `PARK_IT_SITE_DIR`, which is used in the default `mkdocs.yml` config to
            specify the build directory. Defaults to the path specified by
            `PARK_IT_SITE_DIR` if set, else `[CWD]/site/`.
        google_token_path (FilePath | None, optional): Path to the saved Google OAuth
            token JSON file used for refresh and reauthentication. Only required if the
            email waitlist feature is enabled. Defaults to `[CWD]/auth-token.json`.
        waitlist_password_path (FilePath | None, optional): Path to a text file
            containing your chosen shared waitlist password. You can also set this with
            the environment variable `PARK_IT_WAITLIST_PASSWORD`, but a dedicated file
            is more secure. Password is only required if the email waitlist feature is
            enabled. Defaults to None.

    Returns:
        FastAPI: Configured application instance.
    """
    if app_config is DEFAULT:
        app_config = Path.cwd() / DEFAULT_APP_CONFIG_FILE
    if sqlite_dir is DEFAULT:
        sqlite_dir = Path.cwd() / DEFAULT_SQLITE_DIR
    if google_token_path is DEFAULT:
        google_token_path = Path.cwd() / DEFAULT_GOOGLE_TOKEN_FILE
    if site_dir is DEFAULT:
        site_dir = Path(os.getenv("PARK_IT_SITE_DIR", Path.cwd() / DEFAULT_SITE_DIR))

    assert not isinstance(app_config, _Default)
    assert not isinstance(sqlite_dir, _Default)
    assert not isinstance(google_token_path, _Default)
    assert not isinstance(site_dir, _Default)

    if isinstance(app_config, Path):
        app_config = AppConfig.from_yaml(app_config)

    app = _create_app(
        app_config=app_config,
        sqlite_dir=sqlite_dir,
        google_token_path=google_token_path,
        waitlist_password_path=waitlist_password_path,
    )

    app.add_exception_handler(
        RequestValidationError, cast(Any, log_request_validation_error)
    )
    app.add_exception_handler(ValidationError, cast(Any, handle_validation_error))
    app.add_exception_handler(Exception, log_unexpected_exception)

    app.include_router(create_space_router(space_update_model))
    app.include_router(waitlist_form_router)

    # add directory for static built files (including from any markdown files the user added)
    app.mount("/", StaticFiles(directory=site_dir, html=True), name="static")

    return app


@asynccontextmanager
async def app_lifespan(
    app: FastAPI,
    config: AppConfig,
    sqlite_dir: DirectoryPath,
    google_token_path: FilePath | None,
    waitlist_password_path: FilePath | None,
):
    """App lifespan used setting up reminder scheduler and for shutting down dbs."""

    deps = AppDependencies.initialize(
        config, sqlite_dir, google_token_path, waitlist_password_path
    )
    app.state.deps = deps
    if config.waitlist:
        app.state.job_ctx = ScheduledJobContext(config, sqlite_dir, google_token_path)

    try:
        yield

    finally:
        await deps.teardown()


def _create_app(
    app_config: AppConfig,
    sqlite_dir: DirectoryPath,
    google_token_path: FilePath | None,
    waitlist_password_path: FilePath | None,
) -> FastAPI:
    return FastAPI(
        title=app_config.title,
        description=app_config.description,
        version=app_config.version,
        openapi_url=app_config.openapi_url,
        lifespan=partial(
            app_lifespan,
            config=app_config,
            sqlite_dir=sqlite_dir,
            google_token_path=google_token_path,
            waitlist_password_path=waitlist_password_path,
        ),
    )
