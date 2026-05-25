from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from fh6.domain.value_objects.confidence import Confidence
from fh6.domain.value_objects.ids import CarId, SessionId


@dataclass(slots=True)
class FrameRaw:
    """Raw tier — decoded directly from the UDP packet. Mirrors FH6 fields
    documented in `forza-horizon-telemetry-research.md` (offsets 0..322)
    plus the reserved trailing byte at 323 (FR-002).

    `tire_wear` is populated only when the inbound packet carries the
    optional Motorsport-style 4 × f32 wear block at offsets 324..339;
    otherwise None and `tire_wear_source == "modeled"` (the placeholder /
    real model fills `FrameModeled.tire_wear`)."""

    is_race_on: bool
    timestamp_ms: int
    engine: dict[str, float]
    drivetrain: dict[str, Any]
    motion: dict[str, Any]
    inputs: dict[str, float]
    wheels: dict[str, dict[str, float | int]]
    world: dict[str, Any]
    race: dict[str, Any]
    tail_reserved_byte: int
    tire_wear: dict[str, float] | None = None
    tire_wear_source: str = "modeled"


@dataclass(slots=True)
class FrameDerived:
    """Derived tier — deterministic physics from raw."""

    balance: float = 0.0
    weight_front: float = 0.5
    weight_left: float = 0.5
    body_control: float = 0.0
    grip_budget_used: float = 0.0
    power_band_occupancy: float = 0.0
    throttle_smoothness: float = 0.0
    # Projected stopping distance in meters at the current decel rate.
    # 0 when not actually decelerating along the direction of motion.
    stop_distance_m: float = 0.0


@dataclass(slots=True)
class FrameModeled:
    """Modeled tier — ML / LLM output. Per Principle VI every field carries
    its own Confidence. The composite confidence is for the per-frame
    `tireWear` group exposed on the wire (API spec §2)."""

    tire_wear: dict[str, float] = field(
        default_factory=lambda: {"fl": 0.0, "fr": 0.0, "rl": 0.0, "rr": 0.0}
    )
    tire_wear_confidence: Confidence = field(default_factory=Confidence.placeholder)
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DecodedFrame:
    """One UDP packet, sessionized. The unit of live emission and
    lossless persistence (constitution Principles V and VIII)."""

    session_id: SessionId | None
    car_id: CarId
    received_at: datetime
    raw: FrameRaw
    derived: FrameDerived = field(default_factory=FrameDerived)
    modeled: FrameModeled = field(default_factory=FrameModeled)
