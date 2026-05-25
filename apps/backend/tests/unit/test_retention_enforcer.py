"""T081: unit test for RetentionEnforcer (Clarification Q2 / FR-039a)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fh6.application.services.retention_enforcer import (
    RetentionEnforcer,
    RetentionPolicy,
)
from fh6.domain.entities.car import Car
from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.domain.entities.session import Session, SessionCloseReason, SessionType
from fh6.domain.value_objects.ids import CarId, SessionId
from tests.contract.fake_repos import (
    InMemoryCarRepository,
    InMemoryFrameStore,
    InMemorySessionRepository,
)

NOW = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)


def _car(car_id: str) -> Car:
    return Car(
        id=CarId(car_id),
        display_name=car_id,
        short_name=car_id[:4],
        car_ordinal=1,
        car_class="A",
        performance_index=800,
        drivetrain="AWD",
        car_group=0,
    )


def _raw() -> FrameRaw:
    return FrameRaw(
        is_race_on=True,
        timestamp_ms=1000,
        engine={"rpm": 6000.0},
        drivetrain={"gear": 4, "clutch": 0.0, "type": "AWD"},
        motion={"speed_mps": 41.0},
        inputs={
            "throttle": 0.8,
            "brake": 0.0,
            "clutch": 0.0,
            "handbrake": 0.0,
            "steer": 0.0,
            "drivingLine": 0.0,
            "aiBrakeDelta": 0.0,
        },
        wheels={
            wn: {
                "slipRatio": 0.04,
                "slipAngle": 0.07,
                "combinedSlip": 0.09,
                "rotation_rad_s": 96.0,
                "suspensionTravel_norm": 0.5,
                "suspensionTravel_m": 0.07,
                "tireTemp_c": 84.4,
                "tireTemp_normWindow": 0.5,
                "onRumble": 0,
                "inPuddle": 0,
                "surfaceRumble": 0.03,
            }
            for wn in ("fl", "fr", "rl", "rr")
        },
        world={
            "carOrdinal": 1,
            "carClass": "A",
            "performanceIndex": 800,
            "numCylinders": 6,
            "carGroup": 0,
            "smashableVelDiff": 0.0,
            "smashableMass": 0.0,
        },
        race={
            "lap": 0,
            "position": 0,
            "currentLapS": 0.0,
            "lastLapS": None,
            "bestLapS": None,
            "raceTimeS": 0.0,
        },
        tail_reserved_byte=0,
    )


def _seed_session(
    sessions: InMemorySessionRepository,
    frames: InMemoryFrameStore,
    *,
    session_id: str,
    car_id: str,
    started_at: datetime,
    closed: bool = True,
    n_frames: int = 1,
) -> Session:
    s = Session(
        id=SessionId(session_id),
        car_id=CarId(car_id),
        type=SessionType.RACE,
        started_at=started_at,
        ended_at=(started_at + timedelta(minutes=30)) if closed else None,
        duration_s=1800.0 if closed else None,
        closed_reason=SessionCloseReason.SHUTDOWN if closed else None,
    )
    sessions.sessions[str(s.id)] = s
    for _ in range(n_frames):
        frames.frames.setdefault(str(s.id), []).append(
            DecodedFrame(session_id=s.id, car_id=CarId(car_id), received_at=started_at, raw=_raw())
        )
    return s


@pytest.mark.asyncio
async def test_age_based_eviction_only_runs_on_closed_sessions() -> None:
    cars = InMemoryCarRepository()
    sessions = InMemorySessionRepository()
    frames = InMemoryFrameStore()
    cars.cars["car_a"] = _car("car_a")
    old = _seed_session(
        sessions,
        frames,
        session_id="old",
        car_id="car_a",
        started_at=NOW - timedelta(days=200),  # age out
    )
    in_flight = _seed_session(
        sessions,
        frames,
        session_id="open",
        car_id="car_a",
        started_at=NOW - timedelta(days=400),  # would age out, but in-flight
        closed=False,
    )
    enforcer = RetentionEnforcer(
        session_repo=sessions,
        car_repo=cars,
        frame_store=frames,
        policy=RetentionPolicy(retention_days=90, max_bytes_per_car=10**12),
        clock=lambda: NOW,
    )
    run = await enforcer.run_once()
    assert old.id in run.aged_out
    assert in_flight.id not in run.aged_out
    assert run.skipped_in_flight >= 1
    assert str(old.id) not in sessions.sessions
    assert str(in_flight.id) in sessions.sessions


@pytest.mark.asyncio
async def test_per_car_size_cap_evicts_oldest_closed_only() -> None:
    cars = InMemoryCarRepository()
    sessions = InMemorySessionRepository()
    frames = InMemoryFrameStore()
    cars.cars["car_a"] = _car("car_a")
    # 3 closed sessions, 1500 bytes each (1 frame × 1200 + overhead).
    a1 = _seed_session(
        sessions,
        frames,
        session_id="a1",
        car_id="car_a",
        started_at=NOW - timedelta(days=3),
        n_frames=2,
    )
    a2 = _seed_session(
        sessions,
        frames,
        session_id="a2",
        car_id="car_a",
        started_at=NOW - timedelta(days=2),
        n_frames=2,
    )
    a3 = _seed_session(
        sessions,
        frames,
        session_id="a3",
        car_id="car_a",
        started_at=NOW - timedelta(days=1),
        n_frames=2,
    )
    # Cap below total bytes so oldest must be evicted.
    enforcer = RetentionEnforcer(
        session_repo=sessions,
        car_repo=cars,
        frame_store=frames,
        policy=RetentionPolicy(retention_days=10_000, max_bytes_per_car=2 * 1200 + 1),
        clock=lambda: NOW,
    )
    run = await enforcer.run_once()
    # Should evict oldest first.
    assert a1.id in run.capped_out
    assert a3.id not in run.capped_out  # newest preserved
    assert str(a1.id) not in sessions.sessions


@pytest.mark.asyncio
async def test_size_cap_isolates_cars_from_each_other() -> None:
    cars = InMemoryCarRepository()
    sessions = InMemorySessionRepository()
    frames = InMemoryFrameStore()
    cars.cars["car_heavy"] = _car("car_heavy")
    cars.cars["car_light"] = _car("car_light")

    heavy = _seed_session(
        sessions,
        frames,
        session_id="h1",
        car_id="car_heavy",
        started_at=NOW - timedelta(days=1),
        n_frames=10,
    )
    light = _seed_session(
        sessions,
        frames,
        session_id="l1",
        car_id="car_light",
        started_at=NOW - timedelta(days=1),
        n_frames=1,
    )

    enforcer = RetentionEnforcer(
        session_repo=sessions,
        car_repo=cars,
        frame_store=frames,
        policy=RetentionPolicy(retention_days=10_000, max_bytes_per_car=1200),
        clock=lambda: NOW,
    )
    run = await enforcer.run_once()
    # Heavy car should evict; light car untouched (1 frame × 1200 == cap, not >).
    assert heavy.id in run.capped_out
    assert light.id not in run.capped_out
    assert str(light.id) in sessions.sessions


@pytest.mark.asyncio
async def test_combined_age_then_size_pass() -> None:
    cars = InMemoryCarRepository()
    sessions = InMemorySessionRepository()
    frames = InMemoryFrameStore()
    cars.cars["car_a"] = _car("car_a")
    # Old session that ages out; new session that triggers size cap.
    old = _seed_session(
        sessions,
        frames,
        session_id="old",
        car_id="car_a",
        started_at=NOW - timedelta(days=200),
        n_frames=5,
    )
    recent_big = _seed_session(
        sessions,
        frames,
        session_id="big",
        car_id="car_a",
        started_at=NOW - timedelta(days=5),
        n_frames=10,
    )
    recent_keep = _seed_session(
        sessions,
        frames,
        session_id="keep",
        car_id="car_a",
        started_at=NOW - timedelta(days=1),
        n_frames=1,
    )

    enforcer = RetentionEnforcer(
        session_repo=sessions,
        car_repo=cars,
        frame_store=frames,
        policy=RetentionPolicy(retention_days=90, max_bytes_per_car=1200 * 5),
        clock=lambda: NOW,
    )
    run = await enforcer.run_once()
    assert old.id in run.aged_out  # age pass
    # After age pass, `big` (10 frames) still > 5 × 1200 → evicted by size.
    assert recent_big.id in run.capped_out
    assert str(recent_keep.id) in sessions.sessions
