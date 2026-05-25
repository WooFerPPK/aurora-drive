from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fh6.application.services.hot_cache import HotCache
from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.domain.value_objects.ids import CarId, SessionId


def _frame(session_id: str, t: datetime, car_id: str = "car_1_800") -> DecodedFrame:
    raw = FrameRaw(
        is_race_on=True,
        timestamp_ms=0,
        engine={},
        drivetrain={},
        motion={
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "orientation": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
            "speed_mps": 0.0,
        },
        inputs={},
        wheels={},
        world={},
        race={},
        tail_reserved_byte=0,
    )
    return DecodedFrame(
        session_id=SessionId(session_id),
        car_id=CarId(car_id),
        received_at=t,
        raw=raw,
    )


def test_evict_after_drops_frames_strictly_after_threshold() -> None:
    cache = HotCache()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(5):
        cache.append(_frame("s1", t0 + timedelta(seconds=i)))
    # Threshold = t0 + 2s. Frames at t0+3 and t0+4 should be evicted.
    cache.evict_after(SessionId("s1"), t0 + timedelta(seconds=2))
    window = cache.window_for(SessionId("s1"), CarId("car_1_800"))
    times = [f.received_at for f in window]
    assert times == [t0, t0 + timedelta(seconds=1), t0 + timedelta(seconds=2)]


def test_evict_after_updates_latest_to_max_remaining() -> None:
    cache = HotCache()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(4):
        cache.append(_frame("s1", t0 + timedelta(seconds=i)))
    cache.evict_after(SessionId("s1"), t0 + timedelta(seconds=1))
    latest = cache.latest_for(SessionId("s1"), CarId("car_1_800"))
    assert latest is not None
    assert latest.received_at == t0 + timedelta(seconds=1)


def test_evict_after_noop_when_session_absent() -> None:
    cache = HotCache()
    # Must not raise.
    cache.evict_after(SessionId("nope"), datetime(2026, 1, 1, tzinfo=UTC))


def test_evict_after_applies_to_all_cars_in_session() -> None:
    cache = HotCache()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    # Two cars in session "s1", three frames each.
    for i in range(3):
        cache.append(_frame("s1", t0 + timedelta(seconds=i), car_id="car_1"))
        cache.append(_frame("s1", t0 + timedelta(seconds=i), car_id="car_2"))
    # A frame in a different session — must be untouched.
    cache.append(_frame("s2", t0 + timedelta(seconds=2), car_id="car_1"))

    cache.evict_after(SessionId("s1"), t0 + timedelta(seconds=1))

    window_car1 = cache.window_for(SessionId("s1"), CarId("car_1"))
    window_car2 = cache.window_for(SessionId("s1"), CarId("car_2"))
    assert [f.received_at for f in window_car1] == [t0, t0 + timedelta(seconds=1)]
    assert [f.received_at for f in window_car2] == [t0, t0 + timedelta(seconds=1)]

    # Different session untouched.
    other = cache.window_for(SessionId("s2"), CarId("car_1"))
    assert len(other) == 1


def test_evict_after_clears_window_and_latest_when_all_evicted() -> None:
    cache = HotCache()
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(3):
        cache.append(_frame("s1", t0 + timedelta(seconds=i)))

    # Threshold before every frame — all frames must be evicted.
    cache.evict_after(SessionId("s1"), t0 - timedelta(seconds=1))

    assert cache.window_for(SessionId("s1"), CarId("car_1_800")) == []
    assert cache.latest_for(SessionId("s1"), CarId("car_1_800")) is None
