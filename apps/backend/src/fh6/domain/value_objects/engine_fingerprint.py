from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fh6.domain.entities.frame import FrameRaw


def _int_or_none(v: object) -> int | None:
    """Convert a value to int, or None if not convertible.

    Rejects booleans (since bool is a subclass of int in Python).
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    return None


def _str_or_none(v: object) -> str | None:
    """Convert a value to str, or None if falsy or not a string."""
    if isinstance(v, str) and v:
        return v
    return None


@dataclass(frozen=True, slots=True)
class EngineFingerprint:
    """Identifies which engine torque curve applies via exact tune identity.

    All three fields together form a unique fingerprint of the engine setup.
    """

    car_ordinal: int | None
    performance_index: int | None
    num_cylinders: int | None

    @classmethod
    def from_frame_raw(cls, raw: FrameRaw) -> EngineFingerprint:
        """Extract EngineFingerprint from raw frame data.

        Reads carOrdinal, performanceIndex, numCylinders from raw.world.
        Missing or non-numeric values become None.
        """
        return cls(
            car_ordinal=_int_or_none(raw.world.get("carOrdinal")),
            performance_index=_int_or_none(raw.world.get("performanceIndex")),
            num_cylinders=_int_or_none(raw.world.get("numCylinders")),
        )

    def is_complete(self) -> bool:
        """True iff all three fields are non-None."""
        return (
            self.car_ordinal is not None
            and self.performance_index is not None
            and self.num_cylinders is not None
        )


@dataclass(frozen=True, slots=True)
class EngineClassKey:
    """Class-level bucket for cold-start priors on engine torque.

    Groups cars by class, group, drivetrain, and cylinder count.
    """

    car_class: str | None
    car_group: int | None
    drivetrain_type: str | None
    num_cylinders: int | None

    @classmethod
    def from_frame_raw(cls, raw: FrameRaw) -> EngineClassKey:
        """Extract EngineClassKey from raw frame data.

        Reads:
        - carClass from raw.world (string, must be truthy or -> None)
        - carGroup from raw.world (int)
        - type from raw.drivetrain (string, must be truthy or -> None)
        - numCylinders from raw.world (int)
        """
        return cls(
            car_class=_str_or_none(raw.world.get("carClass")),
            car_group=_int_or_none(raw.world.get("carGroup")),
            drivetrain_type=_str_or_none(raw.drivetrain.get("type")),
            num_cylinders=_int_or_none(raw.world.get("numCylinders")),
        )
