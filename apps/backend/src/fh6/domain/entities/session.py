from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from fh6.domain.value_objects.ids import CarId, SessionId, TrackId


class SessionType(StrEnum):
    FREE_ROAM = "free_roam"
    RACE = "race"
    TIME_TRIAL = "time_trial"
    DRIFT = "drift"
    CROSS_COUNTRY = "cross_country"


class SessionState(StrEnum):
    IN_FLIGHT = "in_flight"
    CLOSED = "closed"


class SessionCloseReason(StrEnum):
    CAR_CHANGE = "car_change"
    SILENCE = "silence"
    SHUTDOWN = "shutdown"
    RESTART_FINALIZE = "restart_finalize"  # Clarification Q1
    NOT_IN_EVENT = "not_in_event"


@dataclass(slots=True)
class Session:
    id: SessionId
    car_id: CarId
    type: SessionType
    started_at: datetime
    ended_at: datetime | None = None
    duration_s: float | None = None
    distance_m: float = 0.0
    top_speed_mps: float = 0.0
    lap_count: int = 0
    best_lap_s: float | None = None
    track_id: TrackId | None = None
    summary: str = ""
    style_drift_delta: dict[str, float] = field(default_factory=dict)
    closed_reason: SessionCloseReason | None = None
    name: str | None = None
    bookmarked: bool = False
    # In-memory frame counter used by SessionManager to discard tiny
    # lapless menu fragments on close. Not persisted — reloaded
    # sessions (rewind reopen) start at 0; that's fine because the
    # discard check only fires on fresh closes.
    frame_count: int = 0

    @property
    def state(self) -> SessionState:
        return SessionState.CLOSED if self.ended_at is not None else SessionState.IN_FLIGHT

    def finalize(self, at: datetime, reason: SessionCloseReason) -> None:
        if self.ended_at is not None:
            return  # idempotent; once closed, stays closed
        if at < self.started_at:
            raise ValueError("finalize timestamp precedes session start")
        self.ended_at = at
        self.duration_s = (at - self.started_at).total_seconds()
        self.closed_reason = reason
