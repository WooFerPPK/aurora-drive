"""Contract test for `GET /api/predict/shift` (FR-021, Task 15)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fh6.application.services.hot_cache import HotCache
from fh6.application.services.shift.bin_trainer import BinTrainer
from fh6.application.services.shift.curve_resolver import ShiftCurveResolver
from fh6.application.services.shift.ratio_kalman import RatioKalman
from fh6.application.services.shift.shift_predictor import ShiftPredictor
from fh6.application.services.shift.transmission_mode import TransmissionModeInferer
from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.domain.entities.session import Session, SessionType
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.interfaces.rest.shift_router import router as shift_router
from tests.contract.fake_repos import InMemorySessionRepository, InMemoryShiftPredictorRepo
from tests.unit.test_shift_event_evaluator import _make_config

CAR_ORDINAL = 2451
PERFORMANCE_INDEX = 812
NUM_CYLINDERS = 6


def _raw(*, gear: int = 4, rpm: float = 6500.0) -> FrameRaw:
    return FrameRaw(
        is_race_on=True,
        timestamp_ms=1000,
        engine={
            "rpm": rpm,
            "idleRpm": 900.0,
            "maxRpm": 8000.0,
            "power_w": 250_000.0,
            "torque_nm": 400.0,
            "boost_psi": 0.0,
            "fuel": 0.5,
        },
        drivetrain={"gear": gear, "clutch": 0.0, "type": "AWD"},
        motion={
            "speed_mps": 41.0,
            "velocity": {"x": 0.0, "y": 0.0, "z": 41.0},
            "acceleration": {"x": 0.0, "y": 0.0, "z": 0.0},
            "angularVelocity": {"x": 0.0, "y": 0.0, "z": 0.0},
            "orientation": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        inputs={
            "throttle": 0.99,
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
                "combinedSlip": 0.05,
                "rotation_rad_s": 0.0,
                "suspensionTravel_norm": 0.5,
                "suspensionTravel_m": 0.07,
                "tireTemp_c": 84.0,
                "tireTemp_normWindow": 0.5,
                "onRumble": 0,
                "inPuddle": 0,
                "surfaceRumble": 0.0,
            }
            for wn in ("fl", "fr", "rl", "rr")
        },
        world={
            "carOrdinal": CAR_ORDINAL,
            "carClass": "A",
            "performanceIndex": PERFORMANCE_INDEX,
            "numCylinders": NUM_CYLINDERS,
            "carGroup": 18,
            "smashableVelDiff": 0.0,
            "smashableMass": 0.0,
        },
        race={
            "lap": 1,
            "position": 1,
            "currentLapS": 12.0,
            "lastLapS": None,
            "bestLapS": None,
            "raceTimeS": 30.0,
        },
        tail_reserved_byte=0,
    )


def _frame(*, gear: int = 4, rpm: float = 6500.0) -> DecodedFrame:
    return DecodedFrame(
        session_id=SessionId("live-test"),
        car_id=CarId("car-001"),
        received_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        raw=_raw(gear=gear, rpm=rpm),
    )


class _StubChangePoint:
    def observe(self, *a, **k) -> None: ...
    def reset(self, fp) -> None: ...
    def is_paused(self, fp) -> bool:
        return False


class _StubShiftListener:
    async def on_shift(self, *a, **k) -> None: ...


class _StubClassPrior:
    async def read(self, key):
        return []

    async def maybe_rebuild(self, key, contributing_fp):
        return None


def _make_predictor(repo: InMemoryShiftPredictorRepo) -> ShiftPredictor:
    cfg = _make_config()
    return ShiftPredictor(
        config=cfg,
        repo=repo,
        bin_trainer=BinTrainer(half_life_samples=cfg.shift_ewma_half_life_samples),
        ratio_kalman=RatioKalman(),
        curve_resolver=ShiftCurveResolver(config=cfg),
        class_prior=_StubClassPrior(),
        change_point=_StubChangePoint(),
        shift_listener=_StubShiftListener(),
        transmission_mode_inferer=TransmissionModeInferer(config=cfg),
    )


async def _train_predictor(predictor: ShiftPredictor) -> None:
    """Run enough frames through the predictor that curves resolve."""
    # Stabilise the gear-stable filter
    for _ in range(20):
        await predictor.on_frame(_frame(gear=4), session_uptime_s=120.0, session_type="race")
    # Sweep a range of RPMs to fill bins for gear 4
    for rpm in range(4000, 7800, 50):
        await predictor.on_frame(
            _frame(gear=4, rpm=float(rpm)),
            session_uptime_s=120.0,
            session_type="race",
        )


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    repo = InMemoryShiftPredictorRepo()
    predictor = _make_predictor(repo)
    a.state.session_repo = InMemorySessionRepository()
    a.state.hot_cache = HotCache()
    a.state.shift_predictor = predictor
    a.state.shift_repo = repo
    a.include_router(shift_router, prefix="/api/predict/shift")
    a.state.container = a.state

    return a


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def _seed_live_session(app: FastAPI) -> Session:
    s = Session(
        id=SessionId("live-test"),
        car_id=CarId("car-001"),
        type=SessionType.RACE,
        started_at=datetime(2026, 5, 23, 11, 0, tzinfo=UTC),
        ended_at=None,
    )
    app.state.session_repo.sessions[str(s.id)] = s
    return s


@pytest.mark.asyncio
async def test_predict_shift_returns_fr021_shape(app: FastAPI, client: TestClient) -> None:
    _seed_live_session(app)
    # Seed the hot cache so the router can read the fingerprint.
    frame = _frame()
    app.state.hot_cache.append(frame)

    # Pre-train the predictor by feeding it frames.
    await _train_predictor(app.state.shift_predictor)

    r = client.get("/api/predict/shift?sessionId=live")
    assert r.status_code == 200, r.text
    body = r.json()

    # FR-021 fields
    expected_keys = {
        "fingerprint",
        "byGear",
        "confidenceByGear",
        "ratios",
        "ratioConfidenceByGear",
        "stage",
        "trainedSampleCount",
        "lastUpdated",
        "confidence",
        "inputs",
        "modelVersion",
    }
    assert expected_keys <= set(body.keys()), body
    fp = body["fingerprint"]
    assert fp == {
        "carOrdinal": CAR_ORDINAL,
        "performanceIndex": PERFORMANCE_INDEX,
        "numCylinders": NUM_CYLINDERS,
    }
    assert 0.0 <= float(body["confidence"]) <= 1.0
    assert body["modelVersion"] == "shift-v1"
    assert "engine.torque_nm" in body["inputs"]
    assert body["stage"] in ("learned", "prior", "fallback")
    assert int(body["trainedSampleCount"]) > 0


@pytest.mark.asyncio
async def test_predict_shift_404_when_no_live_session(client: TestClient) -> None:
    r = client.get("/api/predict/shift?sessionId=live")
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_predict_shift_404_when_no_frame_yet(app: FastAPI, client: TestClient) -> None:
    _seed_live_session(app)
    # No hot cache frame seeded
    r = client.get("/api/predict/shift?sessionId=live")
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_predict_shift_fallback_stage_with_cold_predictor(
    app: FastAPI, client: TestClient
) -> None:
    _seed_live_session(app)
    app.state.hot_cache.append(_frame())
    # Do NOT train — predictor is cold.

    r = client.get("/api/predict/shift?sessionId=live")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stage"] == "fallback"
    assert body["byGear"] == {}
    assert body["confidence"] == 0.0
