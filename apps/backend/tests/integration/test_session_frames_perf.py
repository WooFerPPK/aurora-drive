"""T170: perf marker for `/api/sessions/:id/frames` (SC-003).

The full SC-003 measurement requires the `fixtures/packets/thirty_minute_capture.bin`
artifact. CI runs a lighter version: seed 1800 frames in-memory (30 minutes @ 1Hz
equivalent), exercise the projection 50 times, assert p95 < 500 ms locally.

When the full binary fixture lands, raise `N_FRAMES` to match the 30-minute
60 Hz corpus and re-run.
"""

from __future__ import annotations

import statistics
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.domain.entities.session import Session, SessionCloseReason, SessionType
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.interfaces.rest.sessions_router import router as sessions_router
from tests.contract.fake_repos import (
    InMemoryCarRepository,
    InMemoryCoachRepository,
    InMemoryFrameStore,
    InMemorySessionRepository,
)

N_FRAMES = 1800
N_ITERATIONS = 50
P95_BUDGET_MS = 500.0


def _raw(i: int) -> FrameRaw:
    return FrameRaw(
        is_race_on=True,
        timestamp_ms=1000 + i * 16,
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
            "position": {"x": float(i), "y": 0.0, "z": 0.0},
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
            "carOrdinal": 1,
            "carClass": "A",
            "performanceIndex": 800,
            "numCylinders": 6,
            "carGroup": 0,
            "smashableVelDiff": 0.0,
            "smashableMass": 0.0,
        },
        race={
            "lap": 1,
            "position": 1,
            "currentLapS": 1.0,
            "lastLapS": None,
            "bestLapS": None,
            "raceTimeS": 1.0,
        },
        tail_reserved_byte=0,
    )


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    a.state.car_repo = InMemoryCarRepository()
    a.state.session_repo = InMemorySessionRepository()
    a.state.frame_store = InMemoryFrameStore()
    a.state.coach_repo = InMemoryCoachRepository()
    a.include_router(sessions_router, prefix="/api/sessions")

    sid = SessionId("s_perf")
    a.state.session_repo.sessions[str(sid)] = Session(
        id=sid,
        car_id=CarId("car_a"),
        type=SessionType.RACE,
        started_at=datetime(2026, 5, 17, 11, 0, tzinfo=UTC),
        ended_at=datetime(2026, 5, 17, 11, 30, tzinfo=UTC),
        duration_s=1800.0,
        lap_count=20,
        best_lap_s=90.0,
        closed_reason=SessionCloseReason.SHUTDOWN,
    )
    base = datetime(2026, 5, 17, 11, 0, tzinfo=UTC)
    for i in range(N_FRAMES):
        a.state.frame_store.frames.setdefault(str(sid), []).append(
            DecodedFrame(
                session_id=sid,
                car_id=CarId("car_a"),
                received_at=base + timedelta(seconds=i),
                raw=_raw(i),
            )
        )
    a.state.container = a.state
    return a


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_projection_p95_under_500ms(client: TestClient) -> None:
    """SC-003: p95 < 500 ms for projected fetch of a small field set."""
    durations: list[float] = []
    for _ in range(N_ITERATIONS):
        t0 = time.perf_counter()
        r = client.get("/api/sessions/s_perf/frames?fields=speed,throttle,brake&hz=10")
        assert r.status_code == 200
        durations.append((time.perf_counter() - t0) * 1000)
    p95 = statistics.quantiles(durations, n=20)[18]  # ≈ 95th percentile
    assert p95 < P95_BUDGET_MS, (
        f"p95={p95:.1f}ms exceeds SC-003 budget {P95_BUDGET_MS}ms; "
        f"mean={statistics.mean(durations):.1f}ms, max={max(durations):.1f}ms"
    )
