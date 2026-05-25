"""Contract test for `POST /api/predict/shift/reset` (FR-023, Task 17)."""

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
from fh6.domain.entities.session import Session, SessionType
from fh6.domain.ports.shift_predictor_repo import BinRecord, RatioRecord, ShiftEventRow
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.interfaces.rest.shift_router import router as shift_router
from tests.contract.fake_repos import (
    InMemorySessionRepository,
    InMemoryShiftPredictorRepo,
)
from tests.contract.test_predict_shift import _frame
from tests.unit.test_shift_event_evaluator import _make_config

FP = EngineFingerprint(car_ordinal=2451, performance_index=812, num_cylinders=6)
SESSION_ID = SessionId("live-test")


class _StubChangePoint:
    def __init__(self) -> None:
        self.reset_calls: list[EngineFingerprint] = []

    def observe(self, *a, **k) -> None: ...

    def reset(self, fp: EngineFingerprint) -> None:
        self.reset_calls.append(fp)

    def is_paused(self, fp: EngineFingerprint) -> bool:
        return False


class _StubShiftListener:
    async def on_shift(self, *a, **k) -> None: ...


class _StubClassPrior:
    async def read(self, key):
        return []

    async def maybe_rebuild(self, key, contributing_fp):
        return None


def _make_predictor(repo: InMemoryShiftPredictorRepo, change_point):
    cfg = _make_config()
    return ShiftPredictor(
        config=cfg,
        repo=repo,
        bin_trainer=BinTrainer(half_life_samples=cfg.shift_ewma_half_life_samples),
        ratio_kalman=RatioKalman(),
        curve_resolver=ShiftCurveResolver(config=cfg),
        class_prior=_StubClassPrior(),
        change_point=change_point,
        shift_listener=_StubShiftListener(),
        transmission_mode_inferer=TransmissionModeInferer(config=cfg),
    )


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    repo = InMemoryShiftPredictorRepo()
    change_point = _StubChangePoint()
    predictor = _make_predictor(repo, change_point)

    a.state.session_repo = InMemorySessionRepository()
    a.state.hot_cache = HotCache()
    a.state.shift_repo = repo
    a.state.shift_predictor = predictor
    a.state.change_point = change_point
    a.include_router(shift_router, prefix="/api/predict/shift")
    a.state.container = a.state

    return a


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


async def _seed_repo(repo: InMemoryShiftPredictorRepo) -> None:
    now = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
    await repo.upsert_bin(
        BinRecord(
            fingerprint=FP,
            gear=4,
            rpm_bin=65,
            count=120,
            mean_torque_nm=410.0,
            m2_torque=200.0,
            q90_torque_nm=460.0,
            mean_boost_psi=0.0,
            last_updated=now,
        )
    )
    await repo.upsert_ratio(
        RatioRecord(fingerprint=FP, gear=4, ratio=160.0, variance=0.005, last_updated=now)
    )
    await repo.record_shift_event(
        ShiftEventRow(
            id=None,
            session_id=SESSION_ID,
            fingerprint=FP,
            shift_at=now,
            gear_from=3,
            gear_to=4,
            actual_rpm=7100.0,
            recommended_rpm=7200.0,
            recommendation_conf=0.7,
            predicted_post_torque=400.0,
            measured_post_torque=380.0,
            est_cost_s=0.02,
        )
    )


def _seed_live_session(app: FastAPI) -> Session:
    s = Session(
        id=SESSION_ID,
        car_id=CarId("car-001"),
        type=SessionType.RACE,
        started_at=datetime(2026, 5, 23, 11, 0, tzinfo=UTC),
        ended_at=None,
    )
    app.state.session_repo.sessions[str(s.id)] = s
    return s


@pytest.mark.asyncio
async def test_reset_by_explicit_fingerprint(app: FastAPI, client: TestClient) -> None:
    await _seed_repo(app.state.shift_repo)

    r = client.post(
        "/api/predict/shift/reset",
        json={"carOrdinal": 2451, "performanceIndex": 812, "numCylinders": 6},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"]["engineCurves"] == 1
    assert body["deleted"]["shiftEvents"] == 1

    # Repo is now empty for this fingerprint
    assert await app.state.shift_repo.read_bins(FP) == []
    assert await app.state.shift_repo.read_ratios(FP) == []
    assert await app.state.shift_repo.read_shift_events(SESSION_ID) == []


@pytest.mark.asyncio
async def test_reset_by_session_id_live(app: FastAPI, client: TestClient) -> None:
    _seed_live_session(app)
    app.state.hot_cache.append(_frame())
    await _seed_repo(app.state.shift_repo)

    r = client.post(
        "/api/predict/shift/reset",
        json={"sessionId": "live"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"]["engineCurves"] == 1
    assert body["deleted"]["shiftEvents"] == 1

    # Change point reset was also called
    assert app.state.change_point.reset_calls == [FP]


@pytest.mark.asyncio
async def test_reset_response_includes_gear_ratios(app: FastAPI, client: TestClient) -> None:
    """gearRatios must be present in the reset response (v1 omission fix)."""
    await _seed_repo(app.state.shift_repo)

    r = client.post(
        "/api/predict/shift/reset",
        json={"carOrdinal": 2451, "performanceIndex": 812, "numCylinders": 6},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # One RatioRecord was seeded, so gear_ratios should be 1.
    assert "gearRatios" in body["deleted"], f"gearRatios missing from response: {body}"
    assert body["deleted"]["gearRatios"] == 1


@pytest.mark.asyncio
async def test_reset_missing_args_returns_400(app: FastAPI, client: TestClient) -> None:
    r = client.post("/api/predict/shift/reset", json={})
    assert r.status_code == 400, r.text
