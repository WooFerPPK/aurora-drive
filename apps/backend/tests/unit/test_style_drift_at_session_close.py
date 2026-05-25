"""Phase 2c #14: style-drift δ at session close.

Two tiers:

1. `compute_style_drift` — pure helper. Verifies the arithmetic +
   shape rules (intersection with baseline keys; empty input → empty
   output).
2. `IngestFrame._maybe_persist_style_drift` — end-to-end persist
   path with fake `driver_repo` / `build_session_profile` /
   `session_repository`. Asserts the closed session is re-saved with
   the computed δ dict.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from fh6.application.services.hot_cache import HotCache
from fh6.application.services.session_manager import SessionManager
from fh6.application.use_cases.ingest_frame import IngestFrame, compute_style_drift
from fh6.domain.entities.driver_profile import DriverProfile
from fh6.domain.entities.frame import FrameRaw
from tests.contract.fake_repos import InMemoryFrameStore, InMemorySessionRepository


def test_compute_style_drift_subtracts_baseline_from_session() -> None:
    drift = compute_style_drift(
        session_fingerprint={"smooth": 0.7, "patient": 0.4, "brave": 0.55},
        baseline_fingerprint={"smooth": 0.5, "patient": 0.3, "brave": 0.5},
    )
    assert drift["smooth"] == pytest.approx(0.2)
    assert drift["patient"] == pytest.approx(0.1)
    assert drift["brave"] == pytest.approx(0.05)


def test_compute_style_drift_shape_matches_baseline_keys() -> None:
    # Session has an extra trait; baseline drives the result shape.
    drift = compute_style_drift(
        session_fingerprint={"smooth": 0.7, "extra_trait": 1.0},
        baseline_fingerprint={"smooth": 0.5, "patient": 0.3},
    )
    assert set(drift.keys()) == {"smooth", "patient"}
    assert drift["patient"] == pytest.approx(-0.3)  # missing in session → 0


def test_compute_style_drift_empty_inputs_return_empty() -> None:
    assert compute_style_drift({}, {"smooth": 0.5}) == {}
    assert compute_style_drift({"smooth": 0.5}, {}) == {}
    assert compute_style_drift(None, None) == {}


def _raw(*, car_ordinal: int, ts_ms: int) -> FrameRaw:
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
            "lap": 1,
            "position": 1,
            "currentLapS": 1.0,
            "lastLapS": None,
            "bestLapS": None,
            "raceTimeS": 1.0,
        },
        tail_reserved_byte=0,
    )


class _FakeDriverRepo:
    def __init__(self, baseline: dict[str, float]) -> None:
        self._profile = DriverProfile(fingerprint_baseline_90d=dict(baseline))

    async def get(self) -> DriverProfile:
        return self._profile

    async def save(self, profile: DriverProfile) -> None:
        self._profile = profile


class _FakeProfileResult:
    def __init__(self, fingerprint: dict[str, float]) -> None:
        self.fingerprint = dict(fingerprint)


class _FakeBuildSessionProfile:
    def __init__(self, fingerprint: dict[str, float]) -> None:
        self._fp = dict(fingerprint)

    async def __call__(self, _session) -> _FakeProfileResult:  # type: ignore[no-untyped-def]
        return _FakeProfileResult(self._fp)


@pytest.mark.asyncio
async def test_session_close_persists_style_drift_delta() -> None:
    queue: asyncio.Queue = asyncio.Queue()
    sm = SessionManager(silence_seconds=60.0)
    sessions = InMemorySessionRepository()
    frames = InMemoryFrameStore()
    driver_repo = _FakeDriverRepo(baseline={"smooth": 0.5, "patient": 0.3, "brave": 0.5})
    build_session_profile = _FakeBuildSessionProfile(
        fingerprint={"smooth": 0.7, "patient": 0.4, "brave": 0.55}
    )
    ingest = IngestFrame(
        queue=queue,
        session_manager=sm,
        session_repository=sessions,
        frame_store=frames,
        hot_cache=HotCache(),
        driver_repo=driver_repo,
        build_session_profile=build_session_profile,
    )
    ingest.start()
    try:
        t0 = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)
        # Drive car A for 60 frames, then car B → closes A with car_change.
        for i in range(60):
            await queue.put(
                (_raw(car_ordinal=1, ts_ms=1000 + i * 16), t0 + timedelta(milliseconds=i * 16))
            )
        for i in range(5):
            await queue.put(
                (
                    _raw(car_ordinal=2, ts_ms=5000 + i * 16),
                    t0 + timedelta(seconds=5, milliseconds=i * 16),
                )
            )
        for _ in range(200):
            if queue.empty():
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
    finally:
        await ingest.stop()

    # Find the closed (non-shutdown) session — that's the one whose
    # close path ran with both repos wired.
    closed = [s for s in sessions.sessions.values() if s.ended_at is not None]
    assert closed, "expected at least one closed session"
    with_drift = [s for s in closed if s.style_drift_delta]
    assert with_drift, "expected style_drift_delta populated on a closed session"
    drift = with_drift[0].style_drift_delta
    assert drift["smooth"] == pytest.approx(0.2)
    assert drift["patient"] == pytest.approx(0.1)
    assert drift["brave"] == pytest.approx(0.05)
