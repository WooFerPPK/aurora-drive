"""Pydantic wire models for `/api/settings` (API spec §10 + Clarification Q2)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from fh6.infrastructure.telemetry.udp_listener import UDPTelemetryListener
from fh6.interfaces.rest.schemas import WireModel


class TelemetrySettings(WireModel):
    listenAddr: str = "127.0.0.1"
    listenPort: int = 5302
    gameProfile: Literal["fh6"] = "fh6"
    autoDetectCadence: bool = True
    preferredFrameRate: Literal[10, 30, 60] = 30

    @field_validator("listenPort")
    @classmethod
    def _port_not_in_fh6_range(cls, v: int) -> int:
        lo, hi = UDPTelemetryListener.FORBIDDEN_PORT_LOW, UDPTelemetryListener.FORBIDDEN_PORT_HIGH
        if lo <= v <= hi:
            raise ValueError(f"port {v} in FH6 reserved range [{lo}, {hi}]")
        if not (1024 <= v <= 65535):
            raise ValueError(f"port {v} out of [1024, 65535]")
        return v


class ModelsSettings(WireModel):
    llmCoach: bool = True
    tireWearModel: bool = True
    shiftCoach: bool = True
    predictions: bool = True
    drivingFingerprint: bool = True
    voiceCallouts: bool = False
    minCoachPriority: Literal["info", "tip", "warn"] = "tip"


class DataSettings(WireModel):
    recordSessions: bool = True
    storeRawPackets: bool = False
    retentionDays: int = Field(default=90, ge=1)
    shareAnalytics: bool = False  # constitution Principle II — default OFF
    # Clarification Q2 + research R-4
    maxBytesPerCar: int = Field(default=5_368_709_120, ge=100_000_000)


class DisplaySettings(WireModel):
    speedUnit: Literal["kmh", "mph"] = "kmh"
    tempUnit: Literal["f", "c"] = "c"
    reduceMotion: bool = False
    theme: Literal["dark", "light"] = "dark"


class WorldMapCalibration(WireModel):
    """Two reference points mapping FH6 world (X, Z) → tile-pyramid pixel (X, Y).

    Stored as lists for JSON round-trip stability. The widget derives a per-axis
    linear transform from these four pairs; see api-contract §10 + the world_map
    widget for the math.
    """

    aWorld: list[float] = Field(min_length=2, max_length=2)
    aPix: list[float] = Field(min_length=2, max_length=2)
    bWorld: list[float] = Field(min_length=2, max_length=2)
    bPix: list[float] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def _points_not_coincident(self) -> WorldMapCalibration:
        # The per-axis linear transform (api-contract §10) divides by
        # (aWorld - bWorld); a coincident axis would blow it up.
        if self.aWorld[0] == self.bWorld[0]:
            raise ValueError("aWorld and bWorld must differ on the X axis")
        if self.aWorld[1] == self.bWorld[1]:
            raise ValueError("aWorld and bWorld must differ on the Z axis")
        return self


class WorldMapSettings(WireModel):
    """Configuration for the `world_map` widget.

    `calibration` is null until the user runs the in-widget calibration tool
    (capture point A's world coords from telemetry, click pixel A on the map,
    repeat for B). Defaults to the fh6-tel Japan preset so the widget renders
    correctly against the bundled tile pyramid before users run their own
    calibration on the real FH6 map.
    """

    calibration: WorldMapCalibration | None = None


class PerCarOverride(WireModel):
    carId: str
    layoutId: str | None = None
    presetId: str | None = None


class SettingsResponse(WireModel):
    telemetry: TelemetrySettings
    models: ModelsSettings
    data: DataSettings
    display: DisplaySettings
    worldMap: WorldMapSettings = Field(default_factory=WorldMapSettings)
    perCarOverrides: list[PerCarOverride] = Field(default_factory=list)


class SettingsPatch(WireModel):
    """Partial — any subset of the top-level keys."""

    telemetry: TelemetrySettings | None = None
    models: ModelsSettings | None = None
    data: DataSettings | None = None
    display: DisplaySettings | None = None
    worldMap: WorldMapSettings | None = None
    perCarOverrides: list[PerCarOverride] | None = None
