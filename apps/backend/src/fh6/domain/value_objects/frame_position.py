from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class FramePositionSnapshot:
    """A single frame's spatial fingerprint, used by the rewind detector.

    Position units are world metres (matches FH6 telemetry packet).
    Yaw is in radians, in the FH6 coordinate frame.
    """

    time: datetime
    x: float
    y: float
    z: float
    yaw: float
