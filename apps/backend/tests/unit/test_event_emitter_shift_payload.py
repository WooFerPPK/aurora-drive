"""Task 13: extended shift event payload + on_shift_emitted listeners.

Asserts:
- The `shift` event payload includes `rpm` (current frame's RPM).
- When a `ShiftRecommendationProvider` is wired, `recommendedRpm` and
  `recommendationConfidence` are included.
- A provider returning None omits the recommendation fields.
- `add_shift_listener` callbacks fire in registration order with
  `(session_id, prev_frame, current_frame, gear_from, gear_to)`.
- A listener raising does not block subsequent listeners.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fh6.application.services.event_emitter import EventEmitter
from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.domain.value_objects.ids import CarId, SessionId


def _raw(*, gear: int, rpm: float = 6500.0, lap: int = 1) -> FrameRaw:
    return FrameRaw(
        is_race_on=True,
        timestamp_ms=1000,
        engine={"rpm": rpm, "idleRpm": 900.0, "maxRpm": 8000.0},
        drivetrain={"gear": gear, "clutch": 0.0, "type": "AWD"},
        motion={
            "speed_mps": 41.0,
            "velocity": {"x": 0.0, "y": 0.0, "z": 41.0},
            "acceleration": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        inputs={"throttle": 0.99, "brake": 0.0, "clutch": 0.0, "steer": 0.0},
        wheels={
            wn: {"combinedSlip": 0.1, "surfaceRumble": 0.0, "onRumble": 0}
            for wn in ("fl", "fr", "rl", "rr")
        },
        world={"carOrdinal": 2451, "carClass": "A", "performanceIndex": 812, "numCylinders": 6},
        race={"lap": lap, "currentLapS": 12.0, "raceTimeS": 30.0},
        tail_reserved_byte=0,
    )


def _frame(*, gear: int, rpm: float = 6500.0, at: datetime | None = None) -> DecodedFrame:
    at = at or datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
    return DecodedFrame(
        session_id=SessionId("test-session"),
        car_id=CarId("car-001"),
        received_at=at,
        raw=_raw(gear=gear, rpm=rpm),
    )


class _StubProvider:
    def __init__(self, value: tuple[float, float] | None) -> None:
        self.value = value
        self.calls = 0

    def get_recommendation(self, frame: DecodedFrame) -> tuple[float, float] | None:
        self.calls += 1
        return self.value


def _find_shift(events: list[Any]) -> Any:
    for ev in events:
        if ev.kind == "shift":
            return ev
    raise AssertionError("expected a shift event")


def test_shift_payload_includes_rpm() -> None:
    emitter = EventEmitter()
    # Prime previous gear
    emitter.on_frame(_frame(gear=3, rpm=6800))
    out = emitter.on_frame(_frame(gear=4, rpm=6810))

    ev = _find_shift(out)
    assert ev.payload["from"] == 3
    assert ev.payload["to"] == 4
    assert ev.payload["rpm"] == 6810.0


def test_shift_payload_includes_recommendation_when_provider_set() -> None:
    emitter = EventEmitter()
    emitter.set_recommendation_provider(_StubProvider((7100.0, 0.78)))

    emitter.on_frame(_frame(gear=3))
    out = emitter.on_frame(_frame(gear=4))

    ev = _find_shift(out)
    assert ev.payload["recommendedRpm"] == 7100.0
    assert ev.payload["recommendationConfidence"] == 0.78


def test_shift_payload_omits_recommendation_when_provider_returns_none() -> None:
    emitter = EventEmitter()
    emitter.set_recommendation_provider(_StubProvider(None))

    emitter.on_frame(_frame(gear=3))
    out = emitter.on_frame(_frame(gear=4))

    ev = _find_shift(out)
    assert "recommendedRpm" not in ev.payload
    assert "recommendationConfidence" not in ev.payload


def test_shift_payload_omits_recommendation_when_no_provider() -> None:
    emitter = EventEmitter()

    emitter.on_frame(_frame(gear=3))
    out = emitter.on_frame(_frame(gear=4))

    ev = _find_shift(out)
    assert "recommendedRpm" not in ev.payload


def test_shift_listeners_fire_in_registration_order() -> None:
    emitter = EventEmitter()
    calls: list[str] = []

    def listener_a(session_id, prev_frame, current_frame, gear_from, gear_to) -> None:
        calls.append(f"A:{session_id}:{gear_from}->{gear_to}")

    def listener_b(session_id, prev_frame, current_frame, gear_from, gear_to) -> None:
        calls.append(f"B:{session_id}:{gear_from}->{gear_to}")

    emitter.add_shift_listener(listener_a)
    emitter.add_shift_listener(listener_b)

    prev = _frame(gear=3)
    current = _frame(gear=4, at=datetime(2026, 5, 23, 12, 0, 1, tzinfo=UTC))
    emitter.on_frame(prev)
    emitter.on_frame(current)

    assert calls == [
        "A:test-session:3->4",
        "B:test-session:3->4",
    ]


def test_shift_listener_exception_does_not_block_others() -> None:
    emitter = EventEmitter()
    calls: list[str] = []

    def bad(session_id, prev_frame, current_frame, gear_from, gear_to) -> None:
        calls.append("bad")
        raise RuntimeError("boom")

    def good(session_id, prev_frame, current_frame, gear_from, gear_to) -> None:
        calls.append("good")

    emitter.add_shift_listener(bad)
    emitter.add_shift_listener(good)

    emitter.on_frame(_frame(gear=3))
    out = emitter.on_frame(_frame(gear=4))

    assert calls == ["bad", "good"]
    # Event still emitted normally
    _find_shift(out)


def test_shift_listener_receives_prev_and_current_frames() -> None:
    emitter = EventEmitter()
    captured: dict[str, Any] = {}

    def listener(session_id, prev_frame, current_frame, gear_from, gear_to) -> None:
        captured["session_id"] = session_id
        captured["prev"] = prev_frame
        captured["current"] = current_frame
        captured["from"] = gear_from
        captured["to"] = gear_to

    emitter.add_shift_listener(listener)

    prev = _frame(gear=3)
    current_at = datetime(2026, 5, 23, 12, 0, 1, tzinfo=UTC)
    current = _frame(gear=5, at=current_at)
    emitter.on_frame(prev)
    emitter.on_frame(current)

    assert captured["session_id"] == SessionId("test-session")
    assert captured["prev"] is prev
    assert captured["current"] is current
    assert captured["from"] == 3
    assert captured["to"] == 5
