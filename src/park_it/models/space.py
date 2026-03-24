from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum, auto
from typing import Annotated, Self

from pydantic import BaseModel, StringConstraints, field_validator
from sqlmodel import Field, SQLModel

LowerStr = Annotated[str, StringConstraints(to_lower=True)]


class SpaceType(StrEnum):
    """Enumerate the supported parking space categories."""

    EV_CHARGER = "EV charger"
    HANDICAP = auto()
    COMPACT = auto()
    STANDARD = auto()
    MOTORCYCLE = auto()
    TRUCK = auto()


SPACE_TYPE_EMOJIS = {
    SpaceType.EV_CHARGER: "⚡️",
    SpaceType.HANDICAP: "♿️",
    SpaceType.COMPACT: "🚗",
    SpaceType.STANDARD: "🚙",
    SpaceType.MOTORCYCLE: "🏍️",
    SpaceType.TRUCK: "🚛",
}


def get_space_type_emoji(type: SpaceType) -> str:
    """Return the display emoji for a space type.

    Args:
        type (SpaceType): Space type to map to an emoji.

    Returns:
        str: Emoji used in the UI for the provided space type.
    """
    return SPACE_TYPE_EMOJIS[type]


class SpaceConfig(BaseModel):
    """Static configuration for a parking space defined in `AppConfig.spaces`.

    Attributes:
        sensor_id (LowerStr): Unique sensor identifier for the space.
        type (SpaceType): Configured category for the space.
        label (str): Human-readable label shown in the site UI, mapping to
            a label on the parking space that is visible to users.
        out_of_order (bool, optional): Whether the space should be disabled and
            excluded from normal availability handling. Defaults to False.
    """

    sensor_id: LowerStr
    type: SpaceType
    label: str
    out_of_order: bool = False

    def to_model(self) -> SpaceModel:
        """Convert configured metadata into the persisted runtime model. All functional
        spaces are initialized to OCCUPIED on first configuration.

        Returns:
            SpaceModel: Initial database model for the configured space.
        """
        fields = {
            "sensor_id": self.sensor_id,
            "state": (
                SpaceState.OUT_OF_ORDER if self.out_of_order else SpaceState.OCCUPIED
            ),
            "update_time": datetime.now(tz=UTC),
            "type": self.type,
            "label": self.label,
        }
        return SpaceModel.model_validate(fields)


class SpaceState(StrEnum):
    """Enumerate the runtime states a parking space can be in."""

    FREE = auto()
    OCCUPIED = auto()
    OUT_OF_ORDER = auto()


class SpaceModel(SQLModel, table=True):
    """Persist the current runtime state for a parking space.

    Attributes:
        sensor_id (LowerStr): Unique sensor identifier for the space.
        state (SpaceState): Current observed state for the space.
        update_time (datetime): Timestamp of the most recent state update. Must be
            timezone-aware.
        type (SpaceType | None, optional): Configured category for the space, if known.
        label (str | None, optional): Human-readable label for display, if known.
    """

    sensor_id: LowerStr = Field(primary_key=True)
    state: SpaceState
    update_time: datetime
    # NOTE: these should only be None when converting with from SpaceUpdateBaseModel.to_model()
    # TODO: this makes it kinda gross for the sake of this one case
    type: SpaceType | None = None
    # TODO maybe don't store the label in the db, it's mostly constant user config
    label: str | None = None
    # battery: float | None = None
    # rssi: int | None = None

    @field_validator("update_time")
    @classmethod
    def validate_update_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        if value.utcoffset() != timedelta(0):
            raise ValueError("update_time must be naive or UTC")
        return value.astimezone(UTC)

    def seconds_since_last_update(self) -> float:
        """Compute elapsed seconds since the last recorded state update.

        Returns:
            float: Seconds elapsed between `update_time` and now.
        """
        time_diff = datetime.now(tz=UTC) - self.update_time
        return time_diff.total_seconds()


# TODO usage stats CLI
class SpaceUsage(SQLModel, table=True):
    """Store a completed occupied or free interval for a parking space.

    Attributes:
        id (int | None, optional): Primary key for the usage row.
        sensor_id (LowerStr): Unique sensor identifier for the space.
        type (SpaceType): Category of the space whose interval was recorded.
        state (SpaceState): State that the space was in during the recorded interval.
        update_time (datetime): Timestamp of the update that closed the interval.
        duration_sec (float): Duration of the completed interval, in seconds.
    """

    id: int | None = Field(None, primary_key=True)
    sensor_id: LowerStr
    type: SpaceType
    state: SpaceState
    update_time: datetime
    duration_sec: float  # timedelta

    @field_validator("update_time")
    @classmethod
    def validate_update_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        if value.utcoffset() != timedelta(0):
            raise ValueError("update_time must be naive or UTC")
        return value.astimezone(UTC)

    @classmethod
    def from_space_models(cls, updated: SpaceModel, previous: SpaceModel) -> Self:
        """Build a usage row from consecutive space-state snapshots.

        Args:
            updated (SpaceModel): Newer space snapshot that closed the previous interval.
            previous (SpaceModel): Prior space snapshot whose state duration is being
                recorded.

        Returns:
            Self: Usage row describing the elapsed duration of `previous.state`.
        """
        d = {
            "sensor_id": updated.sensor_id,
            "type": updated.type,
            "state": previous.state,
            "update_time": updated.update_time,
            "duration_sec": (
                updated.update_time - previous.update_time
            ).total_seconds(),
        }
        return cls.model_validate(d)
