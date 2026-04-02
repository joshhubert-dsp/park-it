from __future__ import annotations

from datetime import datetime
from functools import cached_property
from typing import Self

from pydantic import (
    BaseModel,
    EmailStr,
    ValidationInfo,
    computed_field,
    model_validator,
)
from sqlmodel import Field, SQLModel

from park_it.models.space import SpaceType


class WaitlistRequest(BaseModel):
    """Waitlist join/leave request submitted from the web form.

    Attributes:
        email (EmailStr): Email address to notify when a matching space becomes
            available.
        password (str): Shared password used to authorize joining the waitlist.
        space_type (SpaceType): Requested category of parking space.
    """

    email: EmailStr
    password: str = Field(exclude=True)
    space_type: SpaceType
    confirmation_email: bool = Field(exclude=True)

    @computed_field
    @cached_property
    def timestamp(self) -> datetime:
        """Generate the join timestamp for the waitlist entry.

        Returns:
            datetime: Current timestamp used when converting the request to an entry.
        """
        return datetime.now()

    @model_validator(mode="after")
    def check_password(self, info: ValidationInfo) -> Self:
        if self.password != (info.context or {}).get("password"):
            raise ValueError("Invalid input")
        return self

    def to_entry(self) -> WaitlistEntry:
        """Convert the validated request into a persisted waitlist entry.

        Returns:
            WaitlistEntry: Waitlist row ready to insert into storage.
        """
        return WaitlistEntry.model_validate(self.model_dump())


class WaitlistEntry(SQLModel, table=True):
    """Persist a waitlist entry for future space-available notifications.

    Attributes:
        id (int | None, optional): Primary key for the waitlist row.
        email (EmailStr): Email address to notify.
        space_type (SpaceType): Requested parking space category.
        timestamp (datetime): Time the user joined the waitlist.
    """

    id: int | None = Field(default=None, primary_key=True)
    email: EmailStr = Field(index=True)
    space_type: SpaceType
    timestamp: datetime
