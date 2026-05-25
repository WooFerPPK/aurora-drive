"""Contract test for POST /api/predict/shift/reset — v2 extension (FR-044).

Verifies that reset also deletes the transmission_modes row and that the
response body includes the ``transmissionModes`` count.
"""

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
from fh6.domain.ports.shift_predictor_repo import TransmissionModeRecord
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint
from fh6.interfaces.rest.shift_router import router as shift_router
from tests.contract.fake_repos import (
    InMemorySessionRepository,
    InMemoryShiftPredictorRepo,
)
from tests.unit.test_shift_event_evaluator import _make_config

FP_A = EngineFingerprint(car_ordinal=9999, performance_index=700, num_cylinders=4)
FP_OTHER = EngineFingerprint(car_ordinal=1111, performance_index=500, num_cylinders=6)


class _StubChangePoint:
    def observe(self, *a, **k) -> None: ...

    def reset(self, fp: EngineFingerprint) -> None: ...

    def is_paused(self, fp: EngineFingerprint) -> bool:
        return False


class _StubShiftListener:
    async def on_shift(self, *a, **k) -> None: ...


class _StubClassPrior:
    async def read(self, key):
        return []

    async def maybe_rebuild(self, key, contributing_fp, **kwargs):
        return None


def _make_predictor(repo: InMemoryShiftPredictorRepo):
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


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    repo = InMemoryShiftPredictorRepo()
    predictor = _make_predictor(repo)

    a.state.session_repo = InMemorySessionRepository()
    a.state.hot_cache = HotCache()
    a.state.shift_repo = repo
    a.state.shift_predictor = predictor
    a.include_router(shift_router, prefix="/api/predict/shift")
    a.state.container = a.state

    return a


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


async def _seed_transmission_mode(
    repo: InMemoryShiftPredictorRepo,
    fp: EngineFingerprint,
) -> None:
    """Insert one transmission_modes row for *fp*."""
    await repo.upsert_transmission_mode(
        TransmissionModeRecord(
            fingerprint=fp,
            mode="manual",
            confidence=0.85,
            sample_count=30,
            last_updated=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        )
    )


@pytest.mark.asyncio
async def test_reset_deletes_transmission_mode_row(app: FastAPI, client: TestClient) -> None:
    """FR-044: reset response includes transmissionModes: 1 after seeding a row."""
    repo: InMemoryShiftPredictorRepo = app.state.shift_repo
    await _seed_transmission_mode(repo, FP_A)

    # Confirm the row exists before reset
    assert await repo.read_transmission_mode(FP_A) is not None

    r = client.post(
        "/api/predict/shift/reset",
        json={
            "carOrdinal": FP_A.car_ordinal,
            "performanceIndex": FP_A.performance_index,
            "numCylinders": FP_A.num_cylinders,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # The new field must be present and equal 1
    assert "transmissionModes" in body["deleted"], body
    assert body["deleted"]["transmissionModes"] == 1

    # The DB row must be gone
    assert await repo.read_transmission_mode(FP_A) is None


@pytest.mark.asyncio
async def test_reset_transmission_mode_count_zero_when_no_row(
    app: FastAPI, client: TestClient
) -> None:
    """FR-044: transmissionModes is 0 when no row existed for the fingerprint."""
    r = client.post(
        "/api/predict/shift/reset",
        json={
            "carOrdinal": FP_A.car_ordinal,
            "performanceIndex": FP_A.performance_index,
            "numCylinders": FP_A.num_cylinders,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"]["transmissionModes"] == 0


@pytest.mark.asyncio
async def test_reset_does_not_delete_other_fingerprint_transmission_mode(
    app: FastAPI, client: TestClient
) -> None:
    """FR-044: reset for FP_A must not touch FP_OTHER's transmission mode row."""
    repo: InMemoryShiftPredictorRepo = app.state.shift_repo
    await _seed_transmission_mode(repo, FP_A)
    await _seed_transmission_mode(repo, FP_OTHER)

    r = client.post(
        "/api/predict/shift/reset",
        json={
            "carOrdinal": FP_A.car_ordinal,
            "performanceIndex": FP_A.performance_index,
            "numCylinders": FP_A.num_cylinders,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["deleted"]["transmissionModes"] == 1

    # FP_A row deleted, FP_OTHER row intact
    assert await repo.read_transmission_mode(FP_A) is None
    assert await repo.read_transmission_mode(FP_OTHER) is not None


@pytest.mark.asyncio
async def test_reset_response_includes_gear_ratios_v2(app: FastAPI, client: TestClient) -> None:
    """gearRatios must be present and non-negative in the v2 reset response."""
    from datetime import UTC, datetime

    from fh6.domain.ports.shift_predictor_repo import RatioRecord

    repo: InMemoryShiftPredictorRepo = app.state.shift_repo
    # Seed one ratio record for FP_A.
    await repo.upsert_ratio(
        RatioRecord(
            fingerprint=FP_A,
            gear=3,
            ratio=150.0,
            variance=0.01,
            last_updated=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        )
    )

    r = client.post(
        "/api/predict/shift/reset",
        json={
            "carOrdinal": FP_A.car_ordinal,
            "performanceIndex": FP_A.performance_index,
            "numCylinders": FP_A.num_cylinders,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "gearRatios" in body["deleted"], f"gearRatios missing from v2 response: {body}"
    assert body["deleted"]["gearRatios"] == 1
