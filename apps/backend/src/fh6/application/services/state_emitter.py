"""Stream-state transition emitter (T054).

Emits `state` messages per API spec §2:
- `driving` — first state after `hello` if frames are flowing.
- `stream-paused` — silence ≥ 250 ms OR 3× cadence (whichever is larger).
- `stream-resumed` — packet returns after a paused interval.
- `stream-lost` — silence ≥ 30 s. Connection stays open (per spec §14).

Driven off frame arrival timestamps + the optional cadence reading from
`CadenceMeter`. Pure logic — the WS layer subscribes to events.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal


class StreamState(StrEnum):
    DRIVING = "driving"
    PAUSED = "stream-paused"
    RESUMED = "stream-resumed"
    LOST = "stream-lost"


StateLiteral = Literal["driving", "stream-paused", "stream-resumed", "stream-lost"]


PAUSE_FLOOR = timedelta(milliseconds=250)
LOST_THRESHOLD = timedelta(seconds=30)
PAUSE_CADENCE_MULTIPLIER = 3.0


@dataclass(slots=True)
class StateChange:
    state: StreamState
    at: datetime
    last_frame_at: datetime | None
    reason: str | None = None


def _pause_threshold(
    cadence_hz: float | None,
    *,
    pause_floor: timedelta = PAUSE_FLOOR,
    multiplier: float = PAUSE_CADENCE_MULTIPLIER,
) -> timedelta:
    if cadence_hz is None or cadence_hz <= 0:
        return pause_floor
    cadence_gap = timedelta(seconds=multiplier / cadence_hz)
    return max(pause_floor, cadence_gap)


class StateEmitter:
    """Tracks the latest observed frame timestamp and emits transitions.

    Usage:
        emitter = StateEmitter()
        change = emitter.on_frame(now, cadence_hz=60.0)  # may emit driving / resumed
        change = emitter.on_tick(now, cadence_hz=60.0)   # may emit paused / lost

    Thresholds are injectable so tests can use shorter intervals than the
    production defaults documented in API spec §2.
    """

    def __init__(
        self,
        *,
        pause_floor: timedelta = PAUSE_FLOOR,
        lost_threshold: timedelta = LOST_THRESHOLD,
        pause_cadence_multiplier: float = PAUSE_CADENCE_MULTIPLIER,
    ) -> None:
        self._state: StreamState | None = None
        self._last_frame_at: datetime | None = None
        self._pause_floor = pause_floor
        self._lost_threshold = lost_threshold
        self._pause_multiplier = pause_cadence_multiplier

    @property
    def state(self) -> StreamState | None:
        return self._state

    @property
    def last_frame_at(self) -> datetime | None:
        return self._last_frame_at

    def on_frame(self, at: datetime, cadence_hz: float | None = None) -> StateChange | None:
        prior_state = self._state
        self._last_frame_at = at
        if prior_state is None:
            self._state = StreamState.DRIVING
            return StateChange(state=StreamState.DRIVING, at=at, last_frame_at=at)
        if prior_state in (StreamState.PAUSED, StreamState.LOST):
            self._state = StreamState.RESUMED
            return StateChange(
                state=StreamState.RESUMED,
                at=at,
                last_frame_at=at,
                reason=f"was {prior_state}",
            )
        if prior_state == StreamState.RESUMED:
            self._state = StreamState.DRIVING
            return StateChange(state=StreamState.DRIVING, at=at, last_frame_at=at)
        return None

    def on_tick(self, now: datetime, cadence_hz: float | None = None) -> StateChange | None:
        """Called by the heartbeat / scheduler loop. Emits paused / lost
        when the silence since last frame crosses thresholds.
        """
        if self._last_frame_at is None:
            return None
        # Match regime to `_last_frame_at` so a naive frame timestamp (the
        # UDP listener stamps naive UTC) never gets subtracted from an
        # aware `datetime.now(UTC)` — that TypeError used to kill _tick_loop.
        if self._last_frame_at.tzinfo is None and now.tzinfo is not None:
            now = now.replace(tzinfo=None)
        elif self._last_frame_at.tzinfo is not None and now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        gap = now - self._last_frame_at
        if gap < timedelta(0):
            return None
        pause_at = _pause_threshold(
            cadence_hz,
            pause_floor=self._pause_floor,
            multiplier=self._pause_multiplier,
        )

        if gap >= self._lost_threshold and self._state != StreamState.LOST:
            self._state = StreamState.LOST
            return StateChange(
                state=StreamState.LOST,
                at=now,
                last_frame_at=self._last_frame_at,
                reason=f"silence >= {self._lost_threshold.total_seconds():.1f}s",
            )
        if gap >= pause_at and self._state not in (StreamState.PAUSED, StreamState.LOST):
            self._state = StreamState.PAUSED
            return StateChange(
                state=StreamState.PAUSED,
                at=now,
                last_frame_at=self._last_frame_at,
                reason=f"silence >= {pause_at.total_seconds() * 1000:.0f}ms",
            )
        return None
