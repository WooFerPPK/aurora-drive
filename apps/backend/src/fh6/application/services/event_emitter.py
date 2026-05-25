"""Event detectors (T055).

Produces the API spec §2 event list:
- `session_started`, `session_ended` — fed by SessionManager boundary decisions.
- `lap_started`, `lap_completed`, `sector_completed` — derived from lap-number
  + lap-time changes per frame.
- `shift`, `missed_upshift` — gear-number transitions; missed-upshift fires
  when RPM hit max for ≥ 200 ms before a delayed upshift.
- `oversteer` — combinedSlip rear > front by margin while moving.
- `off_track` — surface-rumble high on all four wheels OR onRumble all 1.
- `smashable_hit` — `smashableVelDiff` non-zero this tick.

Events are full-fidelity and never downsampled.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from fh6.application.services.session_manager import BoundaryDecision, BoundaryEvent
from fh6.domain.entities.frame import DecodedFrame
from fh6.domain.value_objects.ids import SessionId
from fh6.infrastructure.logging import get_logger

log = get_logger(__name__)


class ShiftRecommendationProvider(Protocol):
    """Reads the predictor's live recommendation at shift-emission time.

    Returns `(recommendedRpm, recommendationConfidence)` or None when the
    predictor has no learned recommendation for the frame's fingerprint.
    """

    def get_recommendation(self, frame: DecodedFrame) -> tuple[float, float] | None: ...


ShiftListener = Callable[[SessionId | None, DecodedFrame, DecodedFrame, int, int], None]


@dataclass(slots=True)
class Event:
    kind: str
    at: datetime
    payload: dict[str, Any] = field(default_factory=dict)


# Tunables. Kept small/explicit so tests can hand-construct boundary cases.
_OVERSTEER_MARGIN = 0.10
_OVERSTEER_MIN_SPEED_MPS = 5.0
_OFF_TRACK_RUMBLE = 0.5
_MISSED_UPSHIFT_RPM_FRACTION = 0.98
_MISSED_UPSHIFT_DWELL_MS = 200


class EventEmitter:
    def __init__(self) -> None:
        self._prev_frame: DecodedFrame | None = None
        self._prev_lap_number: int | None = None
        self._prev_current_lap_s: float | None = None
        self._prev_gear: int | None = None
        self._rpm_max_dwell_start: datetime | None = None
        self._recommendation_provider: ShiftRecommendationProvider | None = None
        self._shift_listeners: list[ShiftListener] = []

    def set_recommendation_provider(self, provider: ShiftRecommendationProvider | None) -> None:
        """Wire a provider that supplies `(recommendedRpm, confidence)` for
        the `shift` event payload. Pass `None` to unset.
        """
        self._recommendation_provider = provider

    def add_shift_listener(self, listener: ShiftListener) -> None:
        """Register a callback fired whenever a `shift` event is emitted.

        Signature: `(session_id, prev_frame, current_frame, gear_from, gear_to)`.
        Listeners fire in registration order. Exceptions are logged and
        swallowed so the rest still fire and `on_frame` itself never raises
        because of a downstream subscriber.
        """
        self._shift_listeners.append(listener)

    def on_boundary(self, decision: BoundaryDecision, at: datetime) -> list[Event]:
        out: list[Event] = []
        if decision.closed_session is not None:
            out.append(
                Event(
                    kind="session_ended",
                    at=decision.closed_session.ended_at or at,
                    payload={
                        "sessionId": str(decision.closed_session.id),
                        "reason": (
                            decision.closed_session.closed_reason.value
                            if decision.closed_session.closed_reason is not None
                            else None
                        ),
                    },
                )
            )
        if decision.opened_session is not None and decision.event == BoundaryEvent.SESSION_STARTED:
            out.append(
                Event(
                    kind="session_started",
                    at=decision.opened_session.started_at,
                    payload={
                        "sessionId": str(decision.opened_session.id),
                        "carId": str(decision.opened_session.car_id),
                        "sessionType": decision.opened_session.type.value,
                    },
                )
            )
            # New session resets lap/gear state.
            self._prev_lap_number = None
            self._prev_current_lap_s = None
            self._prev_gear = None
            self._rpm_max_dwell_start = None
            self._prev_frame = None
        return out

    def on_frame(self, frame: DecodedFrame) -> list[Event]:
        out: list[Event] = []
        raw = frame.raw
        at = frame.received_at

        # Lap events.
        lap_no = int(raw.race["lap"])
        current_lap_s = raw.race["currentLapS"]
        if self._prev_lap_number is None:
            out.append(Event(kind="lap_started", at=at, payload={"lap": lap_no}))
        elif lap_no != self._prev_lap_number:
            payload_completed: dict[str, Any] = {"lap": self._prev_lap_number}
            if raw.race.get("lastLapS") is not None:
                payload_completed["lastLapS"] = raw.race["lastLapS"]
            out.append(Event(kind="lap_completed", at=at, payload=payload_completed))
            out.append(Event(kind="lap_started", at=at, payload={"lap": lap_no}))

        # Sector completion proxy: currentLapS reset to ~0 inside same lap.
        if (
            self._prev_current_lap_s is not None
            and current_lap_s is not None
            and self._prev_current_lap_s > 1.0
            and current_lap_s < 0.5
            and lap_no == self._prev_lap_number
        ):
            out.append(
                Event(
                    kind="sector_completed",
                    at=at,
                    payload={"lap": lap_no, "splitS": self._prev_current_lap_s},
                )
            )

        # Gear shifts.
        gear = int(raw.drivetrain["gear"])
        if self._prev_gear is not None and gear != self._prev_gear:
            rpm_now = float(raw.engine.get("rpm", raw.engine.get("currentRpm", 0.0)))
            payload_shift: dict[str, Any] = {
                "from": self._prev_gear,
                "to": gear,
                "rpm": rpm_now,
            }
            if self._recommendation_provider is not None:
                rec = self._recommendation_provider.get_recommendation(frame)
                if rec is not None:
                    payload_shift["recommendedRpm"] = rec[0]
                    payload_shift["recommendationConfidence"] = rec[1]
            out.append(Event(kind="shift", at=at, payload=payload_shift))

            # Fan out to subscribers. `_prev_frame` is the last frame we saw
            # (may be None on the very first transition after init / boundary).
            if self._prev_frame is not None and self._shift_listeners:
                session_id = frame.session_id
                for listener in self._shift_listeners:
                    try:
                        listener(
                            session_id,
                            self._prev_frame,
                            frame,
                            self._prev_gear,
                            gear,
                        )
                    except Exception:
                        log.exception("shift_listener_error")
            # Missed-upshift retroactive check: previous gear held to redline
            # for ≥ _MISSED_UPSHIFT_DWELL_MS before this shift.
            if (
                gear > self._prev_gear
                and self._rpm_max_dwell_start is not None
                and (at - self._rpm_max_dwell_start).total_seconds() * 1000
                >= _MISSED_UPSHIFT_DWELL_MS
            ):
                out.append(
                    Event(
                        kind="missed_upshift",
                        at=at,
                        payload={
                            "gear": self._prev_gear,
                            "dwellMs": int((at - self._rpm_max_dwell_start).total_seconds() * 1000),
                        },
                    )
                )
            self._rpm_max_dwell_start = None

        # RPM redline dwell tracking.
        rpm = float(raw.engine["rpm"])
        rpm_max = float(raw.engine["maxRpm"])
        if rpm_max > 0 and rpm >= rpm_max * _MISSED_UPSHIFT_RPM_FRACTION:
            if self._rpm_max_dwell_start is None:
                self._rpm_max_dwell_start = at
        else:
            self._rpm_max_dwell_start = None

        # Oversteer.
        speed = float(raw.motion["speed_mps"])
        rear = (
            float(raw.wheels["rl"]["combinedSlip"]) + float(raw.wheels["rr"]["combinedSlip"])
        ) * 0.5
        front = (
            float(raw.wheels["fl"]["combinedSlip"]) + float(raw.wheels["fr"]["combinedSlip"])
        ) * 0.5
        if speed >= _OVERSTEER_MIN_SPEED_MPS and (rear - front) >= _OVERSTEER_MARGIN:
            out.append(
                Event(
                    kind="oversteer",
                    at=at,
                    payload={"frontSlip": front, "rearSlip": rear},
                )
            )

        # Off-track.
        rumble_keys = ("fl", "fr", "rl", "rr")
        if all(
            float(raw.wheels[k]["surfaceRumble"]) >= _OFF_TRACK_RUMBLE for k in rumble_keys
        ) or all(int(raw.wheels[k]["onRumble"]) == 1 for k in rumble_keys):
            out.append(Event(kind="off_track", at=at))

        # Smashable hit.
        vel_diff = float(raw.world.get("smashableVelDiff", 0.0))
        if vel_diff != 0.0:
            out.append(
                Event(
                    kind="smashable_hit",
                    at=at,
                    payload={
                        "velDiff": vel_diff,
                        "mass": float(raw.world.get("smashableMass", 0.0)),
                    },
                )
            )

        self._prev_lap_number = lap_no
        self._prev_current_lap_s = float(current_lap_s) if current_lap_s is not None else None
        self._prev_gear = gear
        self._prev_frame = frame
        return out

    def drain(self, frames: Iterable[DecodedFrame]) -> list[Event]:
        out: list[Event] = []
        for f in frames:
            out.extend(self.on_frame(f))
        return out
