"""Unit tests for RewindDetector.

These tests drive the detector against an in-memory FrameStore fake.
Each test seeds the store with a synthetic frame track, hands the
detector a sequence of "current frames," and asserts on the detector's
classification + truncation calls.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from fh6.application.services.rewind_detector import (
    RewindDetector,
    RewindOutcome,
)
from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.domain.entities.session import Session, SessionType
from fh6.domain.value_objects.ids import CarId, SessionId
from tests.contract.fake_repos import InMemoryFrameStore

SESSION = SessionId("s_test")
CAR = CarId("car_1_800")
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _frame(
    *,
    t: datetime,
    x: float,
    y: float = 0.0,
    z: float = 0.0,
    yaw: float = 0.0,
    is_race_on: bool = True,
) -> DecodedFrame:
    raw = FrameRaw(
        is_race_on=is_race_on,
        timestamp_ms=int(t.timestamp() * 1000),
        engine={},
        drivetrain={},
        motion={
            "position": {"x": x, "y": y, "z": z},
            "orientation": {"yaw": yaw, "pitch": 0.0, "roll": 0.0},
            "speed_mps": 0.0,
        },
        inputs={},
        wheels={},
        world={},
        race={},
        tail_reserved_byte=0,
    )
    return DecodedFrame(session_id=SESSION, car_id=CAR, received_at=t, raw=raw)


def _session() -> Session:
    return Session(id=SESSION, car_id=CAR, type=SessionType.FREE_ROAM, started_at=T0)


def _detector(store: InMemoryFrameStore) -> RewindDetector:
    return RewindDetector(
        frame_store=store,
        continuity_threshold_m=20.0,
        match_tolerance_m=5.0,
        yaw_tolerance_rad=math.pi / 2,
        pause_floor=timedelta(milliseconds=250),
        hot_cache=None,
    )


@pytest.mark.asyncio
async def test_first_frame_never_armed() -> None:
    store = InMemoryFrameStore()
    det = _detector(store)
    f = _frame(t=T0, x=0.0)
    decision = await det.on_frame(f)
    assert decision.outcome == RewindOutcome.NO_ACTION
    assert decision.armed is False


@pytest.mark.asyncio
async def test_continuous_two_frames_not_armed() -> None:
    store = InMemoryFrameStore()
    det = _detector(store)
    await det.on_frame(_frame(t=T0, x=0.0))
    decision = await det.on_frame(_frame(t=T0 + timedelta(milliseconds=33), x=1.0))
    assert decision.armed is False


@pytest.mark.asyncio
async def test_arms_after_long_wall_gap() -> None:
    store = InMemoryFrameStore()
    det = _detector(store)
    await det.on_frame(_frame(t=T0, x=0.0))
    # 400 ms gap > 250 ms pause floor.
    decision = await det.on_frame(_frame(t=T0 + timedelta(milliseconds=400), x=1.0))
    assert decision.armed is True


@pytest.mark.asyncio
async def test_arms_when_previous_frame_is_race_on_false() -> None:
    store = InMemoryFrameStore()
    det = _detector(store)
    await det.on_frame(_frame(t=T0, x=0.0, is_race_on=False))
    decision = await det.on_frame(_frame(t=T0 + timedelta(milliseconds=33), x=1.0))
    assert decision.armed is True


@pytest.mark.asyncio
async def test_armed_but_position_continuous_is_not_teleport() -> None:
    store = InMemoryFrameStore()
    det = _detector(store)
    await det.on_frame(_frame(t=T0, x=0.0))
    # Long gap → armed; but only 3 m delta < 20 m continuity threshold.
    decision = await det.on_frame(_frame(t=T0 + timedelta(milliseconds=400), x=3.0))
    assert decision.armed is True
    assert decision.outcome == RewindOutcome.NO_ACTION


@pytest.mark.asyncio
async def test_armed_and_position_jump_is_classified_teleport() -> None:
    store = InMemoryFrameStore()
    det = _detector(store)
    await det.on_frame(_frame(t=T0, x=0.0))
    # 100 m jump after a 400 ms pause.
    decision = await det.on_frame(_frame(t=T0 + timedelta(milliseconds=400), x=100.0))
    assert decision.armed is True
    # No history to match against → TELEPORT_NO_MATCH (Task 9 will narrow this).
    assert decision.outcome == RewindOutcome.TELEPORT_NO_MATCH


@pytest.mark.asyncio
async def test_3d_distance_uses_all_axes() -> None:
    store = InMemoryFrameStore()
    det = _detector(store)
    await det.on_frame(_frame(t=T0, x=0.0, y=0.0, z=0.0))
    # sqrt(0^2 + 0^2 + 25^2) = 25 m > 20 m threshold.
    decision = await det.on_frame(
        _frame(
            t=T0 + timedelta(milliseconds=400),
            x=0.0,
            y=0.0,
            z=25.0,
        )
    )
    assert decision.armed is True
    assert decision.outcome == RewindOutcome.TELEPORT_NO_MATCH


@pytest.mark.asyncio
async def test_continuity_threshold_is_strict_greater_than() -> None:
    """Distance exactly equal to the continuity threshold is NOT a teleport;
    one micrometre over IS a teleport. Locks the `dist > continuity` boundary."""
    store = InMemoryFrameStore()
    det = _detector(store)
    await det.on_frame(_frame(t=T0, x=0.0))
    # Exactly 20 m — must NOT be a teleport (strict >).
    on_boundary = await det.on_frame(_frame(t=T0 + timedelta(milliseconds=400), x=20.0))
    assert on_boundary.outcome == RewindOutcome.NO_ACTION

    # Reset detector state by using a new detector + appropriate seed,
    # so the next assertion isn't confused by stale state.
    det2 = _detector(store)
    await det2.on_frame(_frame(t=T0, x=0.0))
    just_over = await det2.on_frame(_frame(t=T0 + timedelta(milliseconds=400), x=20.001))
    assert just_over.outcome == RewindOutcome.TELEPORT_NO_MATCH


async def _seed_track(
    store: InMemoryFrameStore, points: list[tuple[float, float, float, float]]
) -> None:
    """Seed the store with a track. `points` is list of (t_offset_s, x, y, yaw)."""
    det = _detector(store)
    for ts_off, x, y, yaw in points:
        f = _frame(t=T0 + timedelta(seconds=ts_off), x=x, y=y, z=0.0, yaw=yaw)
        await det.on_frame(f)
        await store.append(f)


@pytest.mark.asyncio
async def test_match_search_finds_single_match() -> None:
    store = InMemoryFrameStore()
    # Drive 0..100 m in 0.5 s steps; then teleport to x=10 (close to t=5).
    pts = [(0.5 * i, float(i * 10), 0.0, 0.0) for i in range(11)]
    await _seed_track(store, pts)
    det = _detector(store)
    # Replay last frame so the detector has fresh state for sid.
    await det.on_frame(_frame(t=T0 + timedelta(seconds=5.0), x=100.0))
    # Pause and resume near x=10 (matches the t=0.5 frame within 5 m).
    decision = await det.on_frame(
        _frame(
            t=T0 + timedelta(seconds=8.0),
            x=11.0,
            y=0.0,
            z=0.0,
            yaw=0.0,
        )
    )
    assert decision.outcome == RewindOutcome.REWIND_TRUNCATED
    assert decision.match_time == T0 + timedelta(seconds=0.5)


@pytest.mark.asyncio
async def test_match_search_picks_latest_when_loop() -> None:
    store = InMemoryFrameStore()
    # Player drives a loop: passes (50, 0) at t=1 and again at t=5, both heading east (yaw=0).
    pts = [
        (1.0, 50.0, 0.0, 0.0),
        (2.0, 60.0, 5.0, 0.5),
        (3.0, 70.0, 10.0, 1.0),
        (4.0, 60.0, 5.0, 1.5),
        (5.0, 50.0, 0.0, 0.0),
        (6.0, 40.0, -5.0, 0.0),
    ]
    await _seed_track(store, pts)
    det = _detector(store)
    await det.on_frame(_frame(t=T0 + timedelta(seconds=6.0), x=40.0))
    # Rewind back to (50, 0) — should pick t=5, not t=1.
    decision = await det.on_frame(
        _frame(
            t=T0 + timedelta(seconds=9.0),
            x=50.0,
            y=0.0,
            z=0.0,
            yaw=0.0,
        )
    )
    assert decision.outcome == RewindOutcome.REWIND_TRUNCATED
    assert decision.match_time == T0 + timedelta(seconds=5.0)


@pytest.mark.asyncio
async def test_yaw_filter_rejects_wrong_direction_match() -> None:
    store = InMemoryFrameStore()
    # (50, 0) was visited at t=1 heading EAST (yaw=0); the only other
    # candidate exists with yaw=math.pi (heading WEST) at t=5.
    pts = [
        (1.0, 50.0, 0.0, 0.0),
        (2.0, 60.0, 5.0, 1.5),
        (5.0, 50.0, 0.0, math.pi),  # ~180° from resume yaw
        (6.0, 40.0, -5.0, math.pi),
    ]
    await _seed_track(store, pts)
    det = _detector(store)
    await det.on_frame(_frame(t=T0 + timedelta(seconds=6.0), x=40.0))
    # Resume at (50, 0) heading EAST (yaw=0) → t=1 passes yaw filter, t=5 fails.
    decision = await det.on_frame(
        _frame(
            t=T0 + timedelta(seconds=9.0),
            x=50.0,
            y=0.0,
            z=0.0,
            yaw=0.0,
        )
    )
    assert decision.outcome == RewindOutcome.REWIND_TRUNCATED
    assert decision.match_time == T0 + timedelta(seconds=1.0)


@pytest.mark.asyncio
async def test_yaw_wrap_at_pi_treated_as_close() -> None:
    """yaw of (pi - eps) and (-pi + eps) should be ~0 apart, not ~2*pi."""
    store = InMemoryFrameStore()
    pts = [
        (1.0, 50.0, 0.0, math.pi - 0.01),  # ~pi
        (2.0, 60.0, 5.0, 0.0),
    ]
    await _seed_track(store, pts)
    det = _detector(store)
    await det.on_frame(_frame(t=T0 + timedelta(seconds=2.0), x=60.0))
    decision = await det.on_frame(
        _frame(
            t=T0 + timedelta(seconds=5.0),
            x=50.0,
            y=0.0,
            z=0.0,
            yaw=-math.pi + 0.01,
        )
    )
    assert decision.outcome == RewindOutcome.REWIND_TRUNCATED
    assert decision.match_time == T0 + timedelta(seconds=1.0)


@pytest.mark.asyncio
async def test_no_match_is_teleport_no_match() -> None:
    store = InMemoryFrameStore()
    pts = [(0.5 * i, float(i * 10), 0.0, 0.0) for i in range(5)]
    await _seed_track(store, pts)
    det = _detector(store)
    await det.on_frame(_frame(t=T0 + timedelta(seconds=2.0), x=40.0))
    # Teleport to (10000, 10000) — no historical match.
    decision = await det.on_frame(
        _frame(
            t=T0 + timedelta(seconds=5.0),
            x=10000.0,
            y=10000.0,
            z=0.0,
        )
    )
    assert decision.outcome == RewindOutcome.TELEPORT_NO_MATCH
    assert decision.match_time is None


@pytest.mark.asyncio
async def test_on_adopt_loads_last_persisted_snapshot_on_next_frame() -> None:
    store = InMemoryFrameStore()
    # Pre-existing persisted frames for the session (from a prior session lifetime).
    for i in range(3):
        await store.append(
            _frame(
                t=T0 + timedelta(seconds=i),
                x=float(i * 10),
                y=0.0,
                z=0.0,
                yaw=0.1 * i,
            )
        )
    det = _detector(store)
    # Simulate SessionManager.adopt — sync call, no FrameStore read yet.
    det.on_adopt(_session(), T0 + timedelta(seconds=2))
    # Next on_frame loads the baseline (x=20) and runs the teleport check.
    decision = await det.on_frame(
        _frame(
            t=T0 + timedelta(seconds=8),
            x=200.0,  # 180 m from baseline = teleport
        )
    )
    assert decision.armed is True
    # No history within 5 m of x=200 -> TELEPORT_NO_MATCH.
    assert decision.outcome == RewindOutcome.TELEPORT_NO_MATCH


@pytest.mark.asyncio
async def test_on_adopt_with_no_persisted_frames_logs_and_does_not_arm() -> None:
    store = InMemoryFrameStore()
    det = _detector(store)
    det.on_adopt(_session(), T0)
    decision = await det.on_frame(_frame(t=T0 + timedelta(seconds=1), x=100.0))
    # No baseline to compare against -> not armed (FR-009 fallback).
    assert decision.armed is False


@pytest.mark.asyncio
async def test_on_adopt_arms_next_frame_even_with_short_gap() -> None:
    """An adopt() means a pause happened, even if the wall-clock gap is small."""
    store = InMemoryFrameStore()
    for i in range(2):
        await store.append(_frame(t=T0 + timedelta(seconds=i), x=float(i * 10), y=0, z=0))
    det = _detector(store)
    det.on_adopt(_session(), T0 + timedelta(seconds=1))
    # Tiny 30 ms gap - would normally NOT arm.
    decision = await det.on_frame(_frame(t=T0 + timedelta(seconds=1, milliseconds=30), x=1000.0))
    assert decision.armed is True


@pytest.mark.asyncio
async def test_on_adopt_followed_by_continuous_frame_no_teleport() -> None:
    """If the resume position is continuous with the last persisted frame
    (player paused but did not rewind), no truncation happens."""
    store = InMemoryFrameStore()
    for i in range(3):
        await store.append(_frame(t=T0 + timedelta(seconds=i), x=float(i * 10), y=0, z=0))
    det = _detector(store)
    det.on_adopt(_session(), T0 + timedelta(seconds=2))
    # Resume at x=22 - only 2 m from the x=20 baseline.
    decision = await det.on_frame(_frame(t=T0 + timedelta(seconds=5), x=22.0))
    assert decision.armed is True
    assert decision.outcome == RewindOutcome.NO_ACTION
