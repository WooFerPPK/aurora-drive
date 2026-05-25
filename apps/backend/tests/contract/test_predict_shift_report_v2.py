"""Contract test for v2 fields on `GET /api/predict/shift/report` (FR-051, Task 16).

New v2 fields asserted:
- ``assistInterventionPct`` — float in [0,1], always present (0.0 for historical).
- ``byGearPair[*].direction`` — "up" for upshifts, "down" for downshifts.
- Downshift ``avgDeltaRpm`` uses (post_shift_rpm - recommended_post_rpm) convention.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fh6.application.services.shift.shift_predictor import SessionAssistStats
from fh6.domain.entities.session import Session, SessionType
from fh6.domain.ports.shift_predictor_repo import ShiftEventRow
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.interfaces.rest.shift_router import router as shift_router
from tests.contract.fake_repos import (
    InMemorySessionRepository,
    InMemoryShiftPredictorRepo,
)

SESSION_ID = SessionId("s-report-v2")
FP = EngineFingerprint(car_ordinal=2451, performance_index=812, num_cylinders=6)


class _FakeShiftPredictor:
    """Minimal stub: tracks _assist_stats for sessionId="live" source tests."""

    def __init__(self) -> None:
        self._assist_stats: dict[SessionId, SessionAssistStats] = {}

    def get_session_assist_pct(self, session_id: SessionId) -> float:
        stats = self._assist_stats.get(session_id)
        if stats is None:
            return 0.0
        return stats.session_pct()


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    a.state.session_repo = InMemorySessionRepository()
    a.state.shift_repo = InMemoryShiftPredictorRepo()
    a.state.shift_predictor = _FakeShiftPredictor()
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
        car_id=CarId("car-v2-001"),
        type=SessionType.RACE,
        started_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        ended_at=None,
    )
    app.state.session_repo.sessions[str(s.id)] = s
    return s


async def _seed_rows(app: FastAPI) -> None:
    """Seed one upshift and two downshift rows for the session.

    Upshift  3->4: actual 7300, recommended 7100 → delta +200; cost 0.01
    Downshift 3->2 (row A): post_shift_rpm 5100, recommended_post 5000 → delta +100; cost 0.03
    Downshift 3->2 (row B): post_shift_rpm 4800, recommended_post 5000 → delta -200; cost 0.05
    """
    repo = app.state.shift_repo
    rows = [
        # Upshift 3->4
        ShiftEventRow(
            id=None,
            session_id=SESSION_ID,
            fingerprint=FP,
            shift_at=datetime(2026, 5, 23, 12, 1, tzinfo=UTC),
            gear_from=3,
            gear_to=4,
            actual_rpm=7300.0,
            recommended_rpm=7100.0,
            recommendation_conf=0.65,
            predicted_post_torque=380.0,
            measured_post_torque=370.0,
            est_cost_s=0.01,
        ),
        # Downshift 3->2 row A
        ShiftEventRow(
            id=None,
            session_id=SESSION_ID,
            fingerprint=FP,
            shift_at=datetime(2026, 5, 23, 12, 2, tzinfo=UTC),
            gear_from=3,
            gear_to=2,
            actual_rpm=4500.0,
            recommended_rpm=None,
            recommendation_conf=None,
            predicted_post_torque=None,
            measured_post_torque=None,
            est_cost_s=0.03,
            post_shift_rpm=5100.0,
            recommended_post_rpm=5000.0,
        ),
        # Downshift 3->2 row B
        ShiftEventRow(
            id=None,
            session_id=SESSION_ID,
            fingerprint=FP,
            shift_at=datetime(2026, 5, 23, 12, 3, tzinfo=UTC),
            gear_from=3,
            gear_to=2,
            actual_rpm=4400.0,
            recommended_rpm=None,
            recommendation_conf=None,
            predicted_post_torque=None,
            measured_post_torque=None,
            est_cost_s=0.05,
            post_shift_rpm=4800.0,
            recommended_post_rpm=5000.0,
        ),
    ]
    for row in rows:
        await repo.record_shift_event(row)


@pytest.mark.asyncio
async def test_v2_fields_present_and_direction(app: FastAPI, client: TestClient) -> None:
    """assistInterventionPct present; direction correct for up and down pairs."""
    _seed_session(app)
    await _seed_rows(app)

    r = client.get(f"/api/predict/shift/report?sessionId={SESSION_ID}")
    assert r.status_code == 200, r.text
    body = r.json()

    # assistInterventionPct must always be present, float in [0, 1]
    assert "assistInterventionPct" in body
    pct = body["assistInterventionPct"]
    assert isinstance(pct, float)
    assert 0.0 <= pct <= 1.0

    # Historical sessions (no live predictor stats yet) report 0.0
    assert pct == 0.0

    by_pair = body["byGearPair"]
    assert "3->4" in by_pair
    assert "3->2" in by_pair

    assert by_pair["3->4"]["direction"] == "up"
    assert by_pair["3->2"]["direction"] == "down"


@pytest.mark.asyncio
async def test_v2_downshift_avg_delta_rpm(app: FastAPI, client: TestClient) -> None:
    """Downshift avgDeltaRpm uses post_shift_rpm - recommended_post_rpm convention."""
    _seed_session(app)
    await _seed_rows(app)

    r = client.get(f"/api/predict/shift/report?sessionId={SESSION_ID}")
    assert r.status_code == 200, r.text
    body = r.json()

    # 3->2: row A delta = 5100 - 5000 = +100; row B delta = 4800 - 5000 = -200
    # average = (100 + -200) / 2 = -50
    p32 = body["byGearPair"]["3->2"]
    assert p32["avgDeltaRpm"] == pytest.approx(-50.0)


@pytest.mark.asyncio
async def test_v2_assist_pct_from_live_predictor(app: FastAPI, client: TestClient) -> None:
    """assistInterventionPct sourced from predictor when session is in-flight."""
    s = _seed_session(app)
    await _seed_rows(app)

    # Inject a live assist stat for the session
    stats = SessionAssistStats()
    stats.record(False)  # eligible, not intervened
    stats.record(True)  # intervened
    stats.record(False)
    stats.record(True)
    # 2 intervened / 4 total → 0.5
    app.state.shift_predictor._assist_stats[s.id] = stats

    r = client.get(f"/api/predict/shift/report?sessionId={SESSION_ID}")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["assistInterventionPct"] == pytest.approx(0.5)
