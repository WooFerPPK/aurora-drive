"""Pydantic wire models for `/api/sessions` (API spec §3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from fh6.interfaces.rest.schemas import WireModel


class SessionListItem(WireModel):
    id: str
    carId: str
    type: Literal[
        "free_roam",
        "race",
        "time_trial",
        "drift",
        "cross_country",
    ]
    startedAt: datetime
    endedAt: datetime | None = None
    durationS: float | None = None
    lapCount: int = 0
    bestLapS: float | None = None
    topSpeedMps: float = 0.0
    distanceM: float = 0.0
    trackId: str | None = None
    summary: str = ""
    closedReason: str | None = None
    name: str | None = None
    bookmarked: bool = False


class SessionListResponse(WireModel):
    sessions: list[SessionListItem]
    nextCursor: str | None = None


class LapRollup(WireModel):
    lap: int
    timeS: float | None
    sectorTimes: list[float] = Field(default_factory=list)
    topSpeedMps: float = 0.0
    avgThrottle: float = 0.0
    avgBrake: float = 0.0


class CornerStat(WireModel):
    corner: str
    avgEntrySpeedMps: float
    avgApexSpeedMps: float
    avgExitSpeedMps: float


class CalloutSummary(WireModel):
    id: str
    atS: float
    priority: Literal["tip", "info", "warn"]
    text: str


class TimelinePoint(WireModel):
    t: float
    speed: float | None
    throttle: float | None
    brake: float | None


class SessionEventEntry(WireModel):
    """One row from the historical session_events log.

    Drives the highlight-reel / chronological event widget on the
    session-detail page. `atS` is seconds since `startedAt`.
    """

    atS: float
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)


class SessionDetailResponse(WireModel):
    id: str
    carId: str
    type: str
    startedAt: datetime
    endedAt: datetime | None = None
    durationS: float | None = None
    lapCount: int = 0
    bestLapS: float | None = None
    topSpeedMps: float = 0.0
    distanceM: float = 0.0
    trackId: str | None = None
    summary: str = ""
    closedReason: str | None = None
    name: str | None = None
    bookmarked: bool = False
    styleDriftDelta: dict[str, float] = Field(default_factory=dict)
    lapRollups: list[LapRollup] = Field(default_factory=list)
    perCornerStats: list[CornerStat] = Field(default_factory=list)
    callouts: list[CalloutSummary] = Field(default_factory=list)
    timeline10hz: list[TimelinePoint] = Field(default_factory=list)
    events: list[SessionEventEntry] = Field(default_factory=list)


class SessionFramesResponse(WireModel):
    sessionId: str
    hz: Literal[10, 30, 60]
    fields: list[str]
    data: list[list[Any]]


class SessionPatchRequest(WireModel):
    # Both keys optional; `name` may be explicitly null to clear, so this
    # uses a sentinel pattern via model_fields_set on the router side.
    name: str | None = None
    bookmarked: bool | None = None


__all__ = [
    "CalloutSummary",
    "CornerStat",
    "LapRollup",
    "SessionDetailResponse",
    "SessionEventEntry",
    "SessionFramesResponse",
    "SessionListItem",
    "SessionListResponse",
    "SessionPatchRequest",
    "TimelinePoint",
]
