"""Phase 2c #15: per-frame highlight events persisted at ingest.

Replays a handful of synthetic frames through `IngestFrame` with an
in-memory `SessionEventsRepository` wired. Asserts that:

- `lap_completed` produced by the gear / lap-number transition lands
  in the repo;
- the historical `at_s` is referenced to session start (not wall
  clock);
- `lap_started` is filtered out because it lives off the persisted set
  (lifecycle, not highlight).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from fh6.application.services.hot_cache import HotCache
from fh6.application.services.session_manager import SessionManager
from fh6.application.use_cases.ingest_frame import IngestFrame
from fh6.domain.entities.frame import FrameRaw
from tests.contract.fake_repos import (
    InMemoryFrameStore,
    InMemorySessionEventsRepository,
    InMemorySessionRepository,
)


def _raw(*, car_ordinal: int, ts_ms: int, lap: int, current_lap_s: float) -> FrameRaw:
    return FrameRaw(
        is_race_on=True,
        timestamp_ms=ts_ms,
        engine={
            "rpm": 6000.0,
            "idleRpm": 900.0,
            "maxRpm": 8000.0,
            "power_w": 250_000.0,
            "torque_nm": 400.0,
            "boost_psi": 11.0,
            "fuel": 0.5,
        },
        drivetrain={"gear": 4, "clutch": 0.0, "type": "AWD"},
        motion={
            "speed_mps": 41.0,
            "velocity": {"x": 0.0, "y": 0.0, "z": 41.0},
            "acceleration": {"x": 0.0, "y": 0.0, "z": 0.0},
            "angularVelocity": {"x": 0.0, "y": 0.0, "z": 0.0},
            "orientation": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
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
            "carOrdinal": car_ordinal,
            "carClass": "A",
            "performanceIndex": 800,
            "numCylinders": 6,
            "carGroup": 18,
            "smashableVelDiff": 0.0,
            "smashableMass": 0.0,
        },
        race={
            "lap": lap,
            "position": 1,
            "currentLapS": current_lap_s,
            "lastLapS": 65.4 if lap > 0 else None,
            "bestLapS": 65.4 if lap > 0 else None,
            "raceTimeS": ts_ms / 1000.0,
        },
        tail_reserved_byte=0,
    )


@pytest.mark.asyncio
async def test_lap_completed_persisted_with_relative_at_s() -> None:
    queue: asyncio.Queue = asyncio.Queue()
    sm = SessionManager(silence_seconds=60.0)
    sessions = InMemorySessionRepository()
    frames = InMemoryFrameStore()
    events_repo = InMemorySessionEventsRepository()
    ingest = IngestFrame(
        queue=queue,
        session_manager=sm,
        session_repository=sessions,
        frame_store=frames,
        hot_cache=HotCache(),
        session_events_repo=events_repo,
    )
    ingest.start()
    try:
        t0 = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)
        # Frame 0: lap 0 starts.
        await queue.put((_raw(car_ordinal=1, ts_ms=1000, lap=0, current_lap_s=1.0), t0))
        # Frame 1: 2.5 s later, lap rolls to 1 → emits lap_completed for lap 0.
        await queue.put(
            (
                _raw(car_ordinal=1, ts_ms=3500, lap=1, current_lap_s=0.1),
                t0 + timedelta(seconds=2.5),
            )
        )
        for _ in range(200):
            if queue.empty():
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
    finally:
        await ingest.stop()

    # Exactly one session was opened; pull its id to read the repo.
    session_ids = list(sessions.sessions.keys())
    assert session_ids, "expected a session to be opened"
    persisted = await events_repo.list_for_session(session_ids[0])
    kinds = [e.kind for e in persisted]
    # lap_started must NOT appear (filtered).
    assert "lap_started" not in kinds
    # lap_completed must appear.
    assert "lap_completed" in kinds
    lap_done = next(e for e in persisted if e.kind == "lap_completed")
    # at_s is seconds since the session started — should be small (< 5 s).
    assert lap_done.at_s == pytest.approx(2.5, abs=0.05)
    assert lap_done.payload.get("lap") == 0
