"""
You must subclass `SpaceUpdateBaseModel` for the update json payload of your specific
parked car sensor.
"""

from abc import ABC, abstractmethod
from datetime import UTC, datetime

from pydantic import AwareDatetime, BaseModel

from park_it.models.space import LowerStr, SpaceModel, SpaceState


class SpaceUpdateBaseModel(BaseModel, ABC):
    """Abstract base model for device-specific parking sensor payloads.

    Subclasses define how an incoming device message is interpreted as a parking space
    status update. Implementations must decide whether a payload should be processed,
    identify the target sensor, report whether the space is occupied, and expose the
    update timestamp. Method `to_model()` is used internally to convert a validated
    payload into the normalized `SpaceModel` stored by the app.
    """

    @abstractmethod
    def sensor_id(self) -> LowerStr:
        """Return the sensor identifier for the payload.

        Returns:
            LowerStr: Lowercased sensor identifier understood by the app.
        """
        return ""

    @abstractmethod
    def occupied(self) -> bool:
        """Report whether the payload indicates an occupied space.

        Returns:
            bool: `True` when the space is occupied, `False` when free.
        """
        return True

    @abstractmethod
    def update_time(self) -> AwareDatetime:
        """Return the timezone-aware timestamp associated with the payload.

        Returns:
            AwareDatetime: Timestamp for the update, must to be timezone-aware.
        """
        return datetime.now(tz=UTC)

    # TODO some sort of error signalling

    def to_model(self) -> SpaceModel:
        """Convert the payload into the normalized runtime space model.

        Returns:
            SpaceModel: Normalized space update ready for persistence.
        """
        fields = {
            "sensor_id": self.sensor_id(),
            "state": SpaceState.OCCUPIED if self.occupied() else SpaceState.FREE,
            "update_time": self.update_time(),
        }
        return SpaceModel.model_validate(fields)


class DummySpaceUpdate(SpaceUpdateBaseModel):
    """Minimal concrete space update payload used by tests and examples.

    Attributes:
        id (LowerStr): Sensor identifier for the parking space being updated.
        occ (bool): Whether the space is currently occupied.
        dt (AwareDatetime): Timestamp associated with the device update.
    """

    id: LowerStr
    occ: bool
    dt: AwareDatetime

    def sensor_id(self) -> LowerStr:
        return self.id

    def occupied(self) -> bool:
        return self.occ

    def update_time(self) -> AwareDatetime:
        return self.dt
