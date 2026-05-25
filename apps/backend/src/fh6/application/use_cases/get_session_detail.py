"""T075: GET /api/sessions/:id detail aggregator.

Builds lap rollups from real per-lap timing rows (session_laps table),
per-corner stats, callouts produced during the session, and a 10 Hz
timeline. Falls back to synthetic rollups (time_s=None) when no lap
rows exist, so sessions recorded before the migration still render.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fh6.domain.entities.session import Session
from fh6.domain.ports.coach_repository import CoachRepository
from fh6.domain.ports.frame_store import FrameStore
from fh6.domain.ports.lap_repository import LapRepository
from fh6.domain.ports.session_events_repository import SessionEventsRepository
from fh6.domain.ports.session_repository import SessionRepository
from fh6.domain.value_objects.ids import SessionId
from fh6.domain.value_objects.session_event import SessionEvent


@dataclass(slots=True)
class LapRollup:
    lap: int
    time_s: float | None
    sector_times: list[float] = field(default_factory=list)
    top_speed_mps: float = 0.0
    avg_throttle: float = 0.0
    avg_brake: float = 0.0


@dataclass(slots=True)
class CornerStat:
    corner: str
    avg_entry_speed_mps: float
    avg_apex_speed_mps: float
    avg_exit_speed_mps: float


@dataclass(slots=True)
class SessionDetail:
    session: Session
    lap_rollups: list[LapRollup]
    per_corner_stats: list[CornerStat]
    callouts: list[dict[str, object]]
    timeline_10hz: list[dict[str, object]]
    events: list[SessionEvent] = field(default_factory=list)


class GetSessionDetail:
    def __init__(
        self,
        session_repo: SessionRepository,
        frame_store: FrameStore,
        coach_repo: CoachRepository | None = None,
        lap_repo: LapRepository | None = None,
        session_events_repo: SessionEventsRepository | None = None,
    ) -> None:
        self._sessions = session_repo
        self._store = frame_store
        self._coach = coach_repo
        self._laps = lap_repo
        self._events_repo = session_events_repo

    async def __call__(self, session_id: SessionId) -> SessionDetail | None:
        session = await self._sessions.get(session_id)
        if session is None:
            return None

        projection = await self._store.read_projection(
            session_id, hz=10, fields=("speed", "throttle", "brake")
        )
        data = projection.get("data") or []
        timeline = [
            {"t": row[0], "speed": row[1], "throttle": row[2], "brake": row[3]} for row in data
        ]

        rollups: list[LapRollup] = []
        if self._laps is not None:
            laps = await self._laps.list_laps_for_session(session_id)
            if laps:
                for lap in laps:
                    rollups.append(
                        LapRollup(
                            # lap_number is 0-indexed; API uses 1-indexed.
                            lap=lap.lap_number + 1,
                            time_s=lap.lap_time_s,
                            top_speed_mps=session.top_speed_mps,
                        )
                    )

        # Fallback: no lap rows yet (pre-migration sessions or free roam
        # where lap_count is populated from the packet's LapNumber field
        # but no timing was captured). Emit synthetic rollups so the API
        # shape is consistent.
        if not rollups and session.lap_count > 0:
            for n in range(1, session.lap_count + 1):
                rollups.append(
                    LapRollup(
                        lap=n,
                        time_s=None,
                        top_speed_mps=session.top_speed_mps,
                    )
                )

        callouts: list[dict[str, object]] = []
        if self._coach is not None:
            for c in await self._coach.list_callouts(session_id):
                callouts.append(
                    {
                        "id": c.id,
                        "atS": c.at_session_seconds,
                        "priority": c.priority.value,
                        "text": c.text,
                    }
                )

        events: list[SessionEvent] = []
        if self._events_repo is not None:
            try:
                events = await self._events_repo.list_for_session(str(session_id))
            except Exception:
                # Highlight reel is non-critical. A failure here must not
                # 500 the whole session-detail response.
                events = []

        return SessionDetail(
            session=session,
            lap_rollups=rollups,
            per_corner_stats=[],
            callouts=callouts,
            timeline_10hz=timeline,
            events=events,
        )
