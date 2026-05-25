"""Session aggregator + type-inference behaviour.

Pins the fix for the bug where session rows stayed at default values
(distance_m=0, top_speed_mps=0, lap_count=0, best_lap_s=None,
type=race) for the whole session despite frames carrying real
measurements. The contract is:
- distance_m / top_speed_mps / lap_count are monotonic high-water marks
- best_lap_s is the running minimum over positive lap times
- type is inferred from race.raceTimeS, not is_race_on (which only
  signals "game not paused"); free_roam can upgrade to race mid-session
  but never the reverse
- the in-flight session finalizes on silence even without a new frame
  (idle sweep) and on force_finalize at shutdown
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fh6.application.services.session_manager import (
    BoundaryEvent,
    SessionManager,
    _apply_aggregates,
    _session_type_from,
)
from fh6.domain.entities.session import SessionCloseReason, SessionType
from fh6.infrastructure.telemetry.fh6_decoder import FH6PacketDecoder


def _decode(payload: bytes):
    return FH6PacketDecoder().decode(payload)


def test_type_inference_uses_race_time_not_is_race_on(make_packet) -> None:
    # is_race_on=1 + race_time=0 → free_roam (active stream, no race timer).
    raw = _decode(make_packet(IsRaceOn=1, CurrentRaceTime=0.0, LapNumber=0, BestLap=0.0))
    assert _session_type_from(raw) == SessionType.FREE_ROAM

    # is_race_on=1 + race_time>0 + position>0 → race.
    raw = _decode(make_packet(IsRaceOn=1, CurrentRaceTime=42.0, RacePosition=3))
    assert _session_type_from(raw) == SessionType.RACE


def test_type_inference_requires_position_above_zero(make_packet) -> None:
    """Spec Gotcha #1: in free-roam, `RacePosition` is always 0; only an
    actual race assigns one. raceTimeS alone can stay non-zero on stale
    frames returning from a race, so it isn't sufficient on its own.
    Matches Forza/server/enricher.js:89."""
    # is_race_on=1, race timer ticking, no position, no lap clock →
    # still free-roam. (Lap clock running + no position would be
    # Time Trial — covered by test_session_close_grace.)
    raw = _decode(make_packet(IsRaceOn=1, CurrentRaceTime=42.0, RacePosition=0, CurrentLap=0.0))
    assert _session_type_from(raw) == SessionType.FREE_ROAM

    # is_race_on=1, position set, but race timer not started → free-roam.
    raw = _decode(
        make_packet(IsRaceOn=1, CurrentRaceTime=0.0, RacePosition=2, LapNumber=0, BestLap=0.0)
    )
    assert _session_type_from(raw) == SessionType.FREE_ROAM


def test_type_inference_requires_is_race_on(make_packet) -> None:
    # Paused / menu (is_race_on=0) is never race, regardless of other fields.
    raw = _decode(make_packet(IsRaceOn=0, CurrentRaceTime=42.0, RacePosition=3))
    assert _session_type_from(raw) == SessionType.FREE_ROAM


def test_first_frame_seeds_aggregates_and_type(make_packet) -> None:
    sm = SessionManager(silence_seconds=60.0)
    raw = _decode(
        make_packet(
            CurrentRaceTime=10.0,
            Speed=58.0,
            DistanceTraveled=17_858.0,
            LapNumber=2,
            BestLap=87.61,
        )
    )
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)
    d = sm.on_frame(raw, t0)

    s = d.opened_session
    assert s is not None
    assert s.type == SessionType.RACE
    assert s.top_speed_mps == pytest.approx(58.0)
    assert s.distance_m == pytest.approx(17_858.0)
    assert s.lap_count == 2
    assert s.best_lap_s == pytest.approx(87.61)


def test_append_updates_session_in_place_monotonically(make_packet) -> None:
    sm = SessionManager(silence_seconds=60.0)
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)

    sm.on_frame(
        _decode(make_packet(Speed=20.0, DistanceTraveled=100.0, LapNumber=0, BestLap=0.0)),
        t0,
    )
    # Higher speed and lap.
    d2 = sm.on_frame(
        _decode(make_packet(Speed=58.0, DistanceTraveled=2_000.0, LapNumber=1, BestLap=90.0)),
        t0 + timedelta(seconds=5),
    )
    assert d2.event == BoundaryEvent.APPENDED
    assert d2.current_session.top_speed_mps == pytest.approx(58.0)
    assert d2.current_session.distance_m == pytest.approx(2_000.0)
    assert d2.current_session.lap_count == 1
    assert d2.current_session.best_lap_s == pytest.approx(90.0)

    # A frame with WORSE speed/distance/lap MUST NOT regress top-speed
    # or lap. Distance is allowed to ADVANCE via the speed*dt fallback
    # (Gotcha #14) when the game-reported odometer drops below our max;
    # what it must never do is go backwards.
    d3 = sm.on_frame(
        _decode(make_packet(Speed=5.0, DistanceTraveled=1_000.0, LapNumber=0, BestLap=0.0)),
        t0 + timedelta(seconds=10),
    )
    assert d3.current_session.top_speed_mps == pytest.approx(58.0)
    assert d3.current_session.distance_m == pytest.approx(2_000.0 + 5.0 * 5)
    assert d3.current_session.lap_count == 1
    assert d3.current_session.best_lap_s == pytest.approx(90.0)

    # Better best_lap reduces the stored value. Game-reported 2500 now
    # exceeds the integrated running total, so the odometer wins again.
    d4 = sm.on_frame(
        _decode(make_packet(Speed=10.0, DistanceTraveled=2_500.0, LapNumber=2, BestLap=87.61)),
        t0 + timedelta(seconds=15),
    )
    assert d4.current_session.distance_m == pytest.approx(2_500.0)
    assert d4.current_session.best_lap_s == pytest.approx(87.61)
    assert d4.current_session.lap_count == 2


def test_type_upgrades_free_roam_to_race(make_packet) -> None:
    sm = SessionManager(silence_seconds=60.0)
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)

    # Open in free-roam (race timer not running).
    d1 = sm.on_frame(_decode(make_packet(CurrentRaceTime=0.0, LapNumber=0, BestLap=0.0)), t0)
    assert d1.opened_session.type == SessionType.FREE_ROAM

    # Race timer starts ticking → same session, type upgrades to race.
    d2 = sm.on_frame(_decode(make_packet(CurrentRaceTime=5.0)), t0 + timedelta(seconds=2))
    assert d2.event == BoundaryEvent.APPENDED
    assert d2.current_session.type == SessionType.RACE


def test_type_does_not_downgrade_back_to_free_roam(make_packet) -> None:
    # Once a session is marked race, post-race menu screens (raceTime=0)
    # must not flip it back. The session is still the same drive.
    sm = SessionManager(silence_seconds=60.0)
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)

    sm.on_frame(_decode(make_packet(CurrentRaceTime=5.0)), t0)
    d = sm.on_frame(
        _decode(make_packet(CurrentRaceTime=0.0, LapNumber=0, BestLap=0.0)),
        t0 + timedelta(seconds=10),
    )
    assert d.current_session.type == SessionType.RACE


def test_maybe_finalize_idle_closes_silent_session(make_packet) -> None:
    sm = SessionManager(silence_seconds=60.0)
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)

    sm.on_frame(_decode(make_packet()), t0)
    assert sm.current is not None

    # Under threshold — no finalize.
    assert sm.maybe_finalize_idle(t0 + timedelta(seconds=30)) is None
    assert sm.current is not None

    # Past threshold — finalize at last_frame_at with reason=silence.
    closed = sm.maybe_finalize_idle(t0 + timedelta(seconds=120))
    assert closed is not None
    assert closed.closed_reason == SessionCloseReason.SILENCE
    assert closed.ended_at == t0
    assert sm.current is None


def test_distance_falls_back_to_speed_integration_when_odometer_stuck(make_packet) -> None:
    """Spec Gotcha #14: game's `DistanceTraveled` can stay 0 in some
    free-roam states even when the car is moving. The aggregator must
    fall back to integrating speed*dt so distance_m reflects travel."""
    sm = SessionManager(silence_seconds=60.0)
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)

    # Seed at distance=0, moving at 20 m/s.
    sm.on_frame(_decode(make_packet(Speed=20.0, DistanceTraveled=0.0)), t0)
    # 1 s later, game still reports 0 — integrate speed * dt instead.
    d1 = sm.on_frame(
        _decode(make_packet(Speed=20.0, DistanceTraveled=0.0)),
        t0 + timedelta(seconds=1),
    )
    assert d1.current_session.distance_m == pytest.approx(20.0)

    # Another 2 s of motion at 30 m/s while odometer is stuck.
    d2 = sm.on_frame(
        _decode(make_packet(Speed=30.0, DistanceTraveled=0.0)),
        t0 + timedelta(seconds=3),
    )
    assert d2.current_session.distance_m == pytest.approx(20.0 + 30.0 * 2)


def test_distance_prefers_game_reported_when_it_advances(make_packet) -> None:
    """If the game odometer is healthy and growing, integration must
    not double-count: prefer the reported value, fall back only when
    it's behind our running max."""
    sm = SessionManager(silence_seconds=60.0)
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)

    sm.on_frame(_decode(make_packet(Speed=20.0, DistanceTraveled=100.0)), t0)
    d = sm.on_frame(
        _decode(make_packet(Speed=20.0, DistanceTraveled=500.0)),
        t0 + timedelta(seconds=1),
    )
    # Game reports 500, which exceeds 100 + 20*1=120 — take the reported value.
    assert d.current_session.distance_m == pytest.approx(500.0)


def test_apply_aggregates_handles_missing_optional_fields() -> None:
    """Defensive: a packet with bestLapS=None (lap not yet completed)
    must not crash _apply_aggregates."""
    from fh6.domain.entities.frame import FrameRaw
    from fh6.domain.entities.session import Session
    from fh6.domain.value_objects.ids import CarId, SessionId

    raw = FrameRaw(
        is_race_on=True,
        timestamp_ms=0,
        engine={"rpm": 0.0, "idleRpm": 0.0, "maxRpm": 0.0},
        drivetrain={"gear": 0, "type": "AWD"},
        motion={"speed_mps": 30.0},
        inputs={},
        wheels={},
        world={"distanceTraveled": 500.0},
        race={"lap": 0, "raceTimeS": 0.0, "bestLapS": None},
        tail_reserved_byte=0,
    )
    s = Session(
        id=SessionId("s_x"),
        car_id=CarId("car_1_2"),
        type=SessionType.FREE_ROAM,
        started_at=datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC),
    )
    _apply_aggregates(s, raw)
    assert s.top_speed_mps == 30.0
    assert s.distance_m == 500.0
    assert s.lap_count == 0
    assert s.best_lap_s is None
