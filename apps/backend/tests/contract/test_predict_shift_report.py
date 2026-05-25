"""Contract test for `GET /api/predict/shift/report` (FR-022, Task 16)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fh6.application.services.hot_cache import HotCache
from fh6.domain.entities.session import Session, SessionType
from fh6.domain.ports.shift_predictor_repo import ShiftEventRow
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.interfaces.rest.shift_router import router as shift_router
from tests.contract.fake_repos import (
    InMemorySessionRepository,
    InMemoryShiftPredictorRepo,
)

SESSION_ID = SessionId("s-report")
FP = EngineFingerprint(car_ordinal=2451, performance_index=812, num_cylinders=6)


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    a.state.session_repo = InMemorySessionRepository()
    a.state.hot_cache = HotCache()
    a.state.shift_repo = InMemoryShiftPredictorRepo()
    a.state.shift_predictor = None  # not exercised by /report
    a.include_router(shift_router, prefix="/api/predict/shift")
    a.state.container = a.state

    return a


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def _seed_session(app: FastAPI) -> Session:
    s = Session(
        id=SESSION_ID,
        car_id=CarId("car-001"),
        type=SessionType.RACE,
        started_at=datetime(2026, 5, 23, 11, 0, tzinfo=UTC),
        ended_at=None,
    )
    app.state.session_repo.sessions[str(s.id)] = s
    return s


async def _seed_rows(app: FastAPI) -> None:
    repo = app.state.shift_repo
    rows = [
        # 2->3: actual 7100, recommended 7200 → delta -100; cost 0.02
        ShiftEventRow(
            id=None,
            session_id=SESSION_ID,
            fingerprint=FP,
            shift_at=datetime(2026, 5, 23, 11, 1, tzinfo=UTC),
            gear_from=2,
            gear_to=3,
            actual_rpm=7100.0,
            recommended_rpm=7200.0,
            recommendation_conf=0.7,
            predicted_post_torque=400.0,
            measured_post_torque=380.0,
            est_cost_s=0.02,
        ),
        # 2->3: actual 7000, recommended 7200 → delta -200; cost 0.04
        ShiftEventRow(
            id=None,
            session_id=SESSION_ID,
            fingerprint=FP,
            shift_at=datetime(2026, 5, 23, 11, 2, tzinfo=UTC),
            gear_from=2,
            gear_to=3,
            actual_rpm=7000.0,
            recommended_rpm=7200.0,
            recommendation_conf=0.7,
            predicted_post_torque=400.0,
            measured_post_torque=360.0,
            est_cost_s=0.04,
        ),
        # 3->4: actual 7300, recommended 7100 → delta +200; cost 0.01
        ShiftEventRow(
            id=None,
            session_id=SESSION_ID,
            fingerprint=FP,
            shift_at=datetime(2026, 5, 23, 11, 3, tzinfo=UTC),
            gear_from=3,
            gear_to=4,
            actual_rpm=7300.0,
            recommended_rpm=7100.0,
            recommendation_conf=0.65,
            predicted_post_torque=380.0,
            measured_post_torque=370.0,
            est_cost_s=0.01,
        ),
    ]
    for row in rows:
        await repo.record_shift_event(row)


@pytest.mark.asyncio
async def test_shift_report_aggregates_rows(app: FastAPI, client: TestClient) -> None:
    _seed_session(app)
    await _seed_rows(app)

    r = client.get(f"/api/predict/shift/report?sessionId={SESSION_ID}")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["sessionId"] == str(SESSION_ID)
    assert body["totalShifts"] == 3
    assert body["cleanShifts"] == 3
    # Average delta: (-100 + -200 + 200) / 3 = -33.33
    assert body["avgDeltaRpm"] == pytest.approx(-100.0 / 3)
    assert body["estTotalCostS"] == pytest.approx(0.02 + 0.04 + 0.01)

    by_pair = body["byGearPair"]
    assert set(by_pair.keys()) == {"2->3", "3->4"}

    p23 = by_pair["2->3"]
    assert p23["n"] == 2
    assert p23["avgDeltaRpm"] == pytest.approx(-150.0)
    assert p23["avgEstCostS"] == pytest.approx(0.03)

    p34 = by_pair["3->4"]
    assert p34["n"] == 1
    assert p34["avgDeltaRpm"] == pytest.approx(200.0)
    assert p34["avgEstCostS"] == pytest.approx(0.01)

    assert body["modelVersion"] == "shift-v1"


@pytest.mark.asyncio
async def test_shift_report_empty_session(app: FastAPI, client: TestClient) -> None:
    _seed_session(app)
    r = client.get(f"/api/predict/shift/report?sessionId={SESSION_ID}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["totalShifts"] == 0
    assert body["cleanShifts"] == 0
    assert body["byGearPair"] == {}
    assert body["estTotalCostS"] == 0.0
