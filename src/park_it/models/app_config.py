from collections import Counter
from functools import cached_property
from typing import Self

import yaml
from loguru import logger
from pydantic import (
    BaseModel,
    EmailStr,
    HttpUrl,
    NonNegativeInt,
    PositiveInt,
    ValidationError,
    computed_field,
    model_validator,
)

from park_it.models.field_types import ImageFile, YamlPath
from park_it.models.space import SpaceConfig, SpaceType


class AppConfig(BaseModel):
    """Application configuration for `build_app()`.

    An `AppConfig` can be constructed directly or loaded from `app-config.yaml`. It
    defines the parking spaces managed by the app, site metadata, optional waitlist
    behavior, and the runtime settings used to initialize databases and integrations.

    Attributes:
        title (str): Human-readable app title shown in the site and OpenAPI metadata.
        description (str): Short description shown in site and API metadata.
        version (str): Application version string.
        app_email (EmailStr): Google account email used to send waitlist messages.
        app_email_name (str | None, optional): Friendly display name for outbound email.
            Defaults to `title` when omitted.
        app_url (HttpUrl): Public base URL where the app is hosted.
        spaces (list[SpaceConfig]): Configured parking spaces and their static metadata.
        show_individual_spaces (bool, optional): Whether to show the "Spaces" section of
            the page with individual space occupancy statuses and durations, alongside aggregate
            counts. You may want to hide this section if your system has a lot of
            spaces. Defaults to True.
        store_usage_durations (bool, optional): Whether to store occupied and free
            durations for computing median duration and wait-time estimates. Defaults to True.
        usage_median_num (int, optional): Number of recent duration rows per space type
            and state to use when computing median usage. Defaults to 1000.
        waitlist (bool, optional): Whether to enable the email waitlist feature.
            Defaults to True.
        waitlist_free_debounce_minutes (NonNegativeInt, optional): Minutes a space must
            remain free before waitlist notifications begin. Defaults to 1.
        waitlist_interval_minutes (PositiveInt, optional): Minutes between waitlist
            notifications while a space remains free. Defaults to 15.
        contact_email (EmailStr | None, optional): Optional support contact included in
            the site UI and email messages. Defaults to None.
        image (ImageFile | None, optional): Model for a descriptive image to display on
            the site, with required metadata. Defaults to None.
        page_icon (str, optional): The Mkdocs Material stock icon to use for the monitor page in the
            navigation sidebar. Search
            https://squidfunk.github.io/mkdocs-material/reference/icons-emojis/#search
            for all icons available. Defaults to "octicons/eye-24".
        db_echo (bool, optional): Whether SQLite operations should be echoed for
            debugging. Defaults to False.
        openapi_url (str | None, optional): Optional FastAPI OpenAPI path. Set to `None`
            to disable OpenAPI generation. Defaults to None.
    """

    title: str
    description: str
    version: str
    app_email: EmailStr
    app_email_name: str | None = None
    app_url: HttpUrl
    spaces: list[SpaceConfig]
    show_individual_spaces: bool = True
    store_usage_durations: bool = True
    usage_median_num: int = 100
    waitlist: bool = True
    waitlist_free_debounce_minutes: NonNegativeInt = 1
    waitlist_interval_minutes: PositiveInt = 20
    contact_email: EmailStr | None = None
    image: ImageFile | None = None
    page_icon: str = "octicons/eye-24"
    db_echo: bool = False
    openapi_url: str | None = None

    @model_validator(mode="after")
    def normalize_app_email_name(self) -> Self:
        if self.app_email_name is None:
            self.app_email_name = self.title
        return self

    @classmethod
    def from_yaml(cls, path: YamlPath) -> Self:
        """Load application configuration from a YAML file.

        Args:
            path (YamlPath): Valid YAML file defining an `AppConfig`.

        Returns:
            Self: Parsed application configuration.
        """
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls._model_validate_cleanly(data)

    @classmethod
    def _model_validate_cleanly(cls, obj: dict, *, context=None, **kwargs):
        """model_validate overload that adds clean error log"""
        try:
            return super().model_validate(obj, context=context, **kwargs)
        except ValidationError as e:
            logger.error(f"Error loading AppConfig: {e}")
            # Kill the process cleanly; uvicorn will just see a non-zero exit
            raise SystemExit(1) from e

    @computed_field
    @cached_property
    def space_counter(self) -> Counter[SpaceType]:
        """Count configured working spaces by type.

        Returns:
            Counter[SpaceType]: Mapping of space type to configured working-space count.
        """
        return Counter([space.type for space in self.spaces if not space.out_of_order])

    @computed_field
    @cached_property
    def space_types(self) -> list[SpaceType]:
        """List the active configured space types.

        Returns:
            list[SpaceType]: Space types with at least one working configured space.
        """
        return list(self.space_counter.keys())

    @computed_field
    @cached_property
    def total_spaces(self) -> int:
        """Return the total number of configured spaces.

        Returns:
            int: Count of configured spaces, including out-of-order entries.
        """
        return len(self.spaces)
