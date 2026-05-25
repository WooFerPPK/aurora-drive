"""Pydantic wire models for `/ws/live` (API spec §2). Field names match
the spec exactly."""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field

from fh6.interfaces.rest.schemas import WireModel


class Hello(WireModel):
    type: Literal["hello"] = "hello"
    server: str
    capabilities: list[str] = Field(default_factory=list)


class Vec3(WireModel):
    x: float
    y: float
    z: float


class Orientation(WireModel):
    yaw: float
    pitch: float
    roll: float


class RaceBlock(WireModel):
    lap: int
    position: int
    currentLapS: float | None
    lastLapS: float | None
    bestLapS: float | None
    raceTimeS: float


class EngineBlock(WireModel):
    rpm: float
    idleRpm: float
    maxRpm: float
    power_w: float
    torque_nm: float
    boost_psi: float
    fuel: float


class DrivetrainBlock(WireModel):
    gear: int
    clutch: float
    type: str


class MotionBlock(WireModel):
    speed_mps: float
    velocity: Vec3
    acceleration: Vec3
    angularVelocity: Vec3
    orientation: Orientation
    position: Vec3


class InputsBlock(WireModel):
    throttle: float
    brake: float
    clutch: float
    handbrake: float
    steer: float
    drivingLine: float
    aiBrakeDelta: float


class WheelBlock(WireModel):
    slipRatio: float
    slipAngle: float
    combinedSlip: float
    rotation_rad_s: float
    suspensionTravel_norm: float
    suspensionTravel_m: float
    tireTemp_c: float
    tireTemp_normWindow: float
    onRumble: int
    inPuddle: int  # 0/1 boolean per FR-023
    surfaceRumble: float


class WheelsBlock(WireModel):
    fl: WheelBlock
    fr: WheelBlock
    rl: WheelBlock
    rr: WheelBlock


class WorldBlock(WireModel):
    carOrdinal: int
    carClass: str
    performanceIndex: int
    numCylinders: int
    carGroup: int
    smashableVelDiff: float
    smashableMass: float


class DerivedBlock(WireModel):
    balance: float
    weightFront: float
    weightLeft: float
    bodyControl: float
    gripBudgetUsed: float
    powerBandOccupancy: float
    throttleSmoothness: float
    # Kinematic stopping distance at current decel; 0 when not braking.
    stopDistance_m: float = 0.0


class ModeledTireWear(WireModel):
    fl: float
    fr: float
    rl: float
    rr: float


class ShiftRecommendation(WireModel):
    """Per-frame projection of the learned shift recommendation (FR-018)."""

    byGear: dict[str, int]
    confidenceByGear: dict[str, float]
    currentGearTarget: int | None
    currentGearConfidence: float
    displayActive: bool
    stage: Literal["learned", "prior", "fallback"]
    byGearSamples: dict[str, int]
    fingerprint: dict[str, int | None]
    modelVersion: str


class ModeledBlock(WireModel):
    tireWear: ModeledTireWear
    tireWearConfidence: float
    modeledByVersion: str
    shiftRecommendation: ShiftRecommendation | None = None


class Frame(WireModel):
    type: Literal["frame"] = "frame"
    t: float
    sessionId: str
    carId: str
    isRaceOn: bool
    race: RaceBlock
    engine: EngineBlock
    drivetrain: DrivetrainBlock
    motion: MotionBlock
    inputs: InputsBlock
    wheels: WheelsBlock
    world: WorldBlock
    derived: DerivedBlock
    modeled: ModeledBlock


class FrameBatch(WireModel):
    type: Literal["frames"] = "frames"
    batch: list[Frame]


class StateMessage(WireModel):
    type: Literal["state"] = "state"
    state: Literal["driving", "stream-paused", "stream-resumed", "stream-lost"]
    at: float
    lastFrameAt: float | None = None
    reason: str | None = None


class EventMessage(WireModel):
    type: Literal["event"] = "event"
    kind: str
    at: float | None = None
    # Open payload — each event kind has its own fields per API spec §2.
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Heartbeat(WireModel):
    type: Literal["heartbeat"] = "heartbeat"
    at: float


class ClientSubscribe(WireModel):
    type: Literal["subscribe"] = "subscribe"
    topics: list[Literal["frames", "events", "coach"]]


class ClientRateChange(WireModel):
    type: Literal["rate"] = "rate"
    hz: Literal[10, 30, 60]


LiveOutbound = Frame | FrameBatch | StateMessage | EventMessage | Heartbeat | Hello
LiveInbound = ClientSubscribe | ClientRateChange


__all__ = [
    "ClientRateChange",
    "ClientSubscribe",
    "DerivedBlock",
    "DrivetrainBlock",
    "EngineBlock",
    "EventMessage",
    "Frame",
    "FrameBatch",
    "Heartbeat",
    "Hello",
    "InputsBlock",
    "LiveInbound",
    "LiveOutbound",
    "ModeledBlock",
    "ModeledTireWear",
    "MotionBlock",
    "Orientation",
    "RaceBlock",
    "StateMessage",
    "Vec3",
    "WheelBlock",
    "WheelsBlock",
    "WorldBlock",
]
