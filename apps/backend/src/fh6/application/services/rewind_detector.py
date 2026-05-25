"""RewindDetector: position-based rewind detection.

See specs/002-rewind-detector/spec.md for the contract.

Lifecycle: one instance per process. State is keyed by SessionId so
multiple sessions (after car-change splits, etc.) are kept distinct.

Hook points:
- on_frame(): called by IngestFrame for every decoded frame, BEFORE
  the frame is appended to FrameStore + HotCache.
- on_adopt(): called by SessionManager via the adopt-listener hook
  when a session is reopened (in-process check_reopen or boot-time
  resume_session_on_restart).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from fh6.application.services.hot_cache import HotCache
from fh6.domain.entities.frame import DecodedFrame
from fh6.domain.entities.session import Session
from fh6.domain.ports.frame_store import FrameStore
from fh6.domain.value_objects.frame_position import FramePositionSnapshot
from fh6.domain.value_objects.ids import SessionId
from fh6.infrastructure.logging import get_logger

log = get_logger(__name__)


class RewindOutcome(StrEnum):
    NO_ACTION = "no_action"
    REWIND_TRUNCATED = "rewind_truncated"
    TELEPORT_NO_MATCH = "teleport_no_match"


@dataclass(slots=True)
class RewindDecision:
    outcome: RewindOutcome
    armed: bool
    deleted_count: int = 0
    match_time: datetime | None = None


@dataclass(slots=True)
class _SessionState:
    """Per-session detector state."""

    last_position: FramePositionSnapshot | None = None
    last_frame_time: datetime | None = None
    last_is_race_on: bool = True
    armed_next: bool = False  # True after an adopt() until the next on_frame.
    pending_baseline_reload: bool = False


class RewindDetector:
    def __init__(
        self,
        *,
        frame_store: FrameStore,
        continuity_threshold_m: float,
        match_tolerance_m: float,
        yaw_tolerance_rad: float,
        pause_floor: timedelta,
        hot_cache: HotCache | None,
    ) -> None:
        self._store = frame_store
        self._continuity = continuity_threshold_m
        self._tol = match_tolerance_m
        self._yaw_tol = yaw_tolerance_rad
        self._pause_floor = pause_floor
        self._hot = hot_cache
        self._state: dict[SessionId, _SessionState] = {}

    async def on_frame(self, frame: DecodedFrame) -> RewindDecision:
        sid = frame.session_id
        if sid is None:
            return RewindDecision(outcome=RewindOutcome.NO_ACTION, armed=False)
        state = self._state.setdefault(sid, _SessionState())

        if state.pending_baseline_reload:
            try:
                snap = await self._store.read_last_position_snapshot(sid)
            except Exception:
                log.warning(
                    "rewind_detector_adopt_snapshot_read_failed",
                    extra={"session_id": sid},
                    exc_info=True,
                )
                snap = None
            state.pending_baseline_reload = False
            if snap is None:
                # No baseline -> first-frame rule applies; un-arm so the
                # null reference doesn't get used.
                state.armed_next = False
            else:
                state.last_position = snap
                state.last_frame_time = snap.time
                state.last_is_race_on = True

        armed = self._compute_armed(frame, state)
        new_snapshot = _snapshot_from_frame(frame)

        decision = RewindDecision(outcome=RewindOutcome.NO_ACTION, armed=armed)

        if armed and state.last_position is not None:
            dist = _distance3d(new_snapshot, state.last_position)
            if dist > self._tol:
                # Possible rewind or teleport: search historical track for a match.
                is_large_jump = dist > self._continuity
                match = await self._find_latest_match(sid, new_snapshot)
                if match is None:
                    if is_large_jump:
                        decision = RewindDecision(
                            outcome=RewindOutcome.TELEPORT_NO_MATCH, armed=armed
                        )
                        log.info(
                            "rewind_detector_teleport_no_match",
                            extra={
                                "session_id": sid,
                                "resume_pos": (new_snapshot.x, new_snapshot.y, new_snapshot.z),
                            },
                        )
                    # else: small jump, no match → NO_ACTION (already set)
                else:
                    decision = await self._truncate(sid, match, new_snapshot, armed=armed)

        if frame.raw.is_race_on:
            state.last_position = new_snapshot
        state.last_frame_time = frame.received_at
        state.last_is_race_on = bool(frame.raw.is_race_on)
        state.armed_next = False
        return decision

    async def _find_latest_match(
        self, sid: SessionId, resume: FramePositionSnapshot
    ) -> FramePositionSnapshot | None:
        track = await self._store.read_position_track(sid)
        best: FramePositionSnapshot | None = None
        for snap in track:
            d = _distance3d(snap, resume)
            if d > self._tol:
                continue
            if _yaw_delta(snap.yaw, resume.yaw) > self._yaw_tol:
                continue
            # Take latest qualifying snapshot.
            if best is None or snap.time > best.time:
                best = snap
        return best

    async def _truncate(
        self,
        sid: SessionId,
        match: FramePositionSnapshot,
        resume: FramePositionSnapshot,
        *,
        armed: bool,
    ) -> RewindDecision:
        """Delete frames in (match.time, resume.time) exclusive."""
        deleted = await self._store.delete_frames_in_range(
            sid, after=match.time, before=resume.time
        )
        if self._hot is not None:
            try:
                self._hot.evict_after(sid, match.time)
            except Exception:
                log.warning(
                    "rewind_detector_hot_cache_evict_failed",
                    extra={"session_id": sid},
                    exc_info=True,
                )
        log.info(
            "rewind_detector_rewind_truncated",
            extra={
                "session_id": sid,
                "match_time": match.time.isoformat(),
                "resume_time": resume.time.isoformat(),
                "deleted_count": deleted,
                "match_distance_m": _distance3d(match, resume),
            },
        )
        return RewindDecision(
            outcome=RewindOutcome.REWIND_TRUNCATED,
            armed=armed,
            deleted_count=deleted,
            match_time=match.time,
        )

    def _compute_armed(self, frame: DecodedFrame, state: _SessionState) -> bool:
        # First frame in this session: no predecessor, never armed.
        if state.last_frame_time is None:
            return False
        if state.armed_next:
            return True
        gap = frame.received_at - state.last_frame_time
        if gap >= self._pause_floor:
            return True
        return not state.last_is_race_on

    def on_session_closed(self, session_id: SessionId) -> None:
        """Discard per-session state when a session closes (FR-009)."""
        self._state.pop(session_id, None)

    def on_adopt(self, session: Session, _last_frame_at: datetime) -> None:
        """Hook called synchronously by SessionManager when adopt()
        reopens a session.

        Does NOT read FrameStore here (adopt is sync). Instead, marks
        the session state as "pending baseline reload." The next call
        to on_frame for this session loads the baseline from FrameStore
        and runs the teleport check against it. See FR-002 / FR-009.
        """
        sid = session.id
        state = self._state.setdefault(sid, _SessionState())
        state.pending_baseline_reload = True
        state.armed_next = True
        state.last_position = None
        state.last_frame_time = None


def _snapshot_from_frame(frame: DecodedFrame) -> FramePositionSnapshot:
    pos = frame.raw.motion.get("position") or {}
    orient = frame.raw.motion.get("orientation") or {}
    return FramePositionSnapshot(
        time=frame.received_at,
        x=float(pos.get("x", 0.0)),
        y=float(pos.get("y", 0.0)),
        z=float(pos.get("z", 0.0)),
        yaw=float(orient.get("yaw", 0.0)),
    )


def _distance3d(a: FramePositionSnapshot, b: FramePositionSnapshot) -> float:
    dx = a.x - b.x
    dy = a.y - b.y
    dz = a.z - b.z
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _yaw_delta(a: float, b: float) -> float:
    """Shortest-angular-distance between two yaw angles in radians.
    Returns a value in [0, π]."""
    raw = abs(a - b) % (2 * math.pi)
    return raw if raw <= math.pi else (2 * math.pi - raw)
