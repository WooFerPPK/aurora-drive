"""Pydantic wire models for `/api/cars` (API spec §4)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from fh6.interfaces.rest.schemas import WireModel


class CarBestLap(WireModel):
    trackId: str
    bestLapS: float


class CarSummary(WireModel):
    id: str
    display: str
    short: str
    ordinal: int
    carClass: str = Field(serialization_alias="class")
    pi: int
    drivetrain: Literal["FWD", "RWD", "AWD"]
    group: int
    groupLabel: str | None = None  # FR-020
    lastSeenAt: datetime | None = None
    sessionCount: int = 0
    totalSecondsDriven: float = 0.0
    bestLapByTrack: list[CarBestLap] = Field(default_factory=list)


class CarListResponse(WireModel):
    cars: list[CarSummary]


class CarRenameRequest(WireModel):
    display_name: str = Field(min_length=1, max_length=120, alias="displayName")


class CarRenameResponse(WireModel):
    ordinal: int
    displayName: str
    shortName: str
    updated: int


class SectorBest(WireModel):
    sector: int
    bestS: float


class PerCornerAverage(WireModel):
    corner: str
    avgEntrySpeedMps: float
    avgApexSpeedMps: float
    avgExitSpeedMps: float


class TirePeakByCorner(WireModel):
    corner: str
    peakTemp: float


class PreferredGearByCorner(WireModel):
    corner: str
    gear: int


class CarAggregateResponse(WireModel):
    carId: str
    lapsTotal: int = 0
    sectorBests: list[SectorBest] = Field(default_factory=list)
    perCornerAverages: list[PerCornerAverage] = Field(default_factory=list)
    shift: dict[str, float] = Field(default_factory=dict)
    tirePeakUseByCorner: list[TirePeakByCorner] = Field(default_factory=list)
    preferredGearByCorner: list[PreferredGearByCorner] = Field(default_factory=list)
    gripBudgetCeiling: float = 0.0
    thisCarSpecificStyle: dict[str, float] = Field(default_factory=dict)


__all__ = [
    "CarAggregateResponse",
    "CarBestLap",
    "CarListResponse",
    "CarRenameRequest",
    "CarRenameResponse",
    "CarSummary",
    "PerCornerAverage",
    "PreferredGearByCorner",
    "SectorBest",
    "TirePeakByCorner",
]
