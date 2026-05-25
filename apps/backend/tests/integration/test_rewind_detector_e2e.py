"""End-to-end: IngestFrame + RewindDetector + InMemoryFrameStore.

A synthesized stream of frames simulates a free-roam drive, a pause,
and a resume at an earlier position. Expectation: the frames between
the match point and the resume are deleted from the store.
"""

from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime, timedelta

import pytest

from fh6.application.services.hot_cache import HotCache
from fh6.application.services.rewind_detector import RewindDetector
from fh6.application.services.session_manager import SessionManager
from fh6.application.use_cases.ingest_frame import IngestFrame
from fh6.domain.entities.frame import FrameRaw
from tests.contract.fake_repos import (
    InMemoryCarRepository,
    InMemoryFrameStore,
    InMemorySessionRepository,
)


def _raw(
    *,
    x: float,
    y: float = 0.0,
    z: float = 0.0,
    yaw: float = 0.0,
    is_race_on: bool = True,
    ts_ms: int = 0,
) -> FrameRaw:
    return FrameRaw(
        is_race_on=is_race_on,
        timestamp_ms=ts_ms,
        engine={
            "rpm": 6000.0,
            "idleRpm": 900.0,
            "maxRpm": 8000.0,
            "power_w": 0.0,
            "torque_nm": 0.0,
            "boost_psi": 0.0,
            "fuel": 0.5,
        },
        drivetrain={"gear": 4, "clutch": 0.0, "type": "AWD"},
        motion={
            "position": {"x": x, "y": y, "z": z},
            "orientation": {"yaw": yaw, "pitch": 0.0, "roll": 0.0},
            "speed_mps": 0.0,
            "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
            "acceleration": {"x": 0.0, "y": 0.0, "z": 0.0},
            "angularVelocity": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        inputs={
            "throttle": 0.5,
            "brake": 0.0,
            "clutch": 0.0,
            "handbrake": 0.0,
            "steer": 0.0,
            "drivingLine": 0.0,
            "aiBrakeDelta": 0.0,
        },
        wheels={
            wn: {
                "slipRatio": 0.0,
                "slipAngle": 0.0,
                "combinedSlip": 0.0,
                "rotation_rad_s": 0.0,
                "suspensionTravel_norm": 0.5,
                "suspensionTravel_m": 0.07,
                "tireTemp_c": 80.0,
                "tireTemp_normWindow": 0.5,
                "onRumble": 0,
                "inPuddle": 0,
                "surfaceRumble": 0.0,
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
            "distanceTraveled": 0.0,
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


@pytest.mark.asyncio
async def test_rewind_truncates_frames_between_match_and_resume() -> None:
    sm = SessionManager(silence_seconds=60.0)
    store = InMemoryFrameStore()
    hot = HotCache()
    detector = RewindDetector(
        frame_store=store,
        continuity_threshold_m=20.0,
        match_tolerance_m=5.0,
        yaw_tolerance_rad=math.pi / 2,
        pause_floor=timedelta(milliseconds=250),
        hot_cache=hot,
    )
    # Sync listener — on_adopt is sync, no asyncio dispatch needed.
    sm.add_adopt_listener(detector.on_adopt)
    queue: asyncio.Queue = asyncio.Queue()
    ingest = IngestFrame(
        queue=queue,
        session_manager=sm,
        session_repository=InMemorySessionRepository(),
        frame_store=store,
        hot_cache=hot,
        car_repository=InMemoryCarRepository(),
        lap_repository=None,
        tire_wear_model=None,
        rewind_detector=detector,
    )

    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    # Drive 11 frames at 33 ms cadence, x = i*10 from 0..100.
    for i in range(11):
        await ingest._handle_one(_raw(x=float(i * 10)), t0 + timedelta(milliseconds=33 * i))
    # 400 ms pause then resume at x=10 (matches frame i=1).
    await ingest._handle_one(
        _raw(x=11.0),
        t0 + timedelta(milliseconds=33 * 10 + 400),
    )

    # Pull all snapshots from the store for the one session that was opened.
    sessions = list(store.frames.keys())  # InMemoryFrameStore uses `frames` (public attr)
    assert len(sessions) == 1
    track = await store.read_position_track(sessions[0])
    xs = [s.x for s in track]
    # Frames 2..10 (x=20..100) should be gone; 0..1 + resume frame remain.
    assert xs == [0.0, 10.0, 11.0]
