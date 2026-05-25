"""Pydantic wire models for `/api/track` (API spec §8)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from fh6.interfaces.rest.schemas import WireModel


class TrackCurrentResponse(WireModel):
    trackId: str
    displayName: str
    inferred: bool = True
    confirmedName: str | None = None
    confirmedAt: datetime | None = None
    outline: list[list[float]] = Field(default_factory=list)
    corners: list[dict[str, Any]] = Field(default_factory=list)


class OptimalLinePoint(WireModel):
    t: float
    x: float
    y: float
    speed: float
    throttle: float
    brake: float


class SectorDelta(WireModel):
    sector: int
    deltaS: float


class IncidentMark(WireModel):
    atS: float
    kind: str
    text: str | None = None


class OptimalLineResponse(WireModel):
    sessionId: str
    trackId: str
    optimalLine: list[OptimalLinePoint] = Field(default_factory=list)
    yourLine: list[OptimalLinePoint] = Field(default_factory=list)
    incidents: list[IncidentMark] = Field(default_factory=list)
    sectorDeltas: list[SectorDelta] = Field(default_factory=list)


class MistakeBucket(WireModel):
    pos: list[float]  # [x, y]
    kind: str
    count: int
    corner: str | None = None


class MistakeBreakdown(WireModel):
    kind: str
    count: int


class MistakeTrendPoint(WireModel):
    dayIso: str
    count: int


class MistakesHeatmapResponse(WireModel):
    carId: str
    trackId: str | None
    buckets: list[MistakeBucket] = Field(default_factory=list)
    breakdown: list[MistakeBreakdown] = Field(default_factory=list)
    trend: list[MistakeTrendPoint] = Field(default_factory=list)


__all__ = [
    "IncidentMark",
    "MistakeBreakdown",
    "MistakeBucket",
    "MistakeTrendPoint",
    "MistakesHeatmapResponse",
    "OptimalLinePoint",
    "OptimalLineResponse",
    "SectorDelta",
    "TrackCurrentResponse",
]
