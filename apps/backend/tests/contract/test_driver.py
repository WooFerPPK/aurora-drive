"""T153: contract test for `/api/driver` (API spec §5)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fh6.domain.entities.car import Car
from fh6.domain.entities.session import Session, SessionCloseReason, SessionType
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.interfaces.rest.driver_router import router as driver_router
from tests.contract.fake_repos import (
    InMemoryCarRepository,
    InMemoryDriverRepository,
    InMemorySessionRepository,
)


def _seed(app: FastAPI, n_sessions: int = 5) -> None:
    car_repo: InMemoryCarRepository = app.state.car_repo
    sess_repo: InMemorySessionRepository = app.state.session_repo
    car = Car(
        id=CarId("car_a"),
        display_name="A",
        short_name="a",
        car_ordinal=1,
        car_class="A",
        performance_index=800,
        drivetrain="AWD",
        car_group=0,
    )
    car_repo.cars[str(car.id)] = car
    base = datetime(2026, 5, 17, 11, 0, tzinfo=UTC)
    for i in range(n_sessions):
        s = Session(
            id=SessionId(f"s_{i}"),
            car_id=car.id,
            type=SessionType.RACE,
            started_at=base + timedelta(days=i),
            ended_at=base + timedelta(days=i, hours=1),
            duration_s=3600.0,
            distance_m=12_000.0,
            lap_count=10,
            best_lap_s=68.0 + i * 0.1,
            top_speed_mps=85.0,
            closed_reason=SessionCloseReason.SHUTDOWN,
        )
        sess_repo.sessions[str(s.id)] = s


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    a.state.car_repo = InMemoryCarRepository()
    a.state.session_repo = InMemorySessionRepository()
    a.state.driver_repo = InMemoryDriverRepository()
    a.include_router(driver_router, prefix="/api/driver")
    a.state.container = a.state

    return a


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_profile_shape_and_trait_range(app: FastAPI, client: TestClient) -> None:
    _seed(app, n_sessions=5)
    r = client.get("/api/driver/profile")
    assert r.status_code == 200
    body = r.json()
    for key in (
        "lapsAnalyzed",
        "distanceAnalyzedM",
        "secondsAnalyzed",
        "fingerprint",
        "traits",
        "strengths",
        "weaknesses",
        "carAgnosticShare",
        "persona",
        "modelVersion",
    ):
        assert key in body
    assert body["lapsAnalyzed"] == 50
    assert body["distanceAnalyzedM"] == 60_000.0
    assert body["secondsAnalyzed"] == 18_000.0
    assert body["modelVersion"].startswith("driver-fingerprint-v")
    for t in body["traits"]:
        assert 0.0 <= t["score"] <= 1.0
    for v in body["fingerprint"].values():
        assert 0.0 <= v <= 1.0


def test_profile_empty_when_no_sessions(app: FastAPI, client: TestClient) -> None:
    """No driving data → well-shaped but empty payload, no phantom persona/weaknesses."""
    r = client.get("/api/driver/profile")
    assert r.status_code == 200
    body = r.json()
    assert body["lapsAnalyzed"] == 0
    assert body["distanceAnalyzedM"] == 0.0
    assert body["secondsAnalyzed"] == 0.0
    assert all(v == 0.0 for v in body["fingerprint"].values())
    assert body["traits"] == []
    assert body["strengths"] == []
    assert body["weaknesses"] == []
    assert body["persona"] == ""


def test_session_driver_profile(app: FastAPI) -> None:
    """Per-session profile uses the same model with a single-session input."""
    from fastapi.testclient import TestClient

    from fh6.interfaces.rest.sessions_router import router as sessions_router

    app.include_router(sessions_router, prefix="/api/sessions")
    _seed(app, n_sessions=3)
    with TestClient(app) as c:
        r = c.get("/api/sessions/s_0/driver-profile")
        assert r.status_code == 200
        body = r.json()
        # Single session: 1 hour, 12km, 10 laps.
        assert body["lapsAnalyzed"] == 10
        assert body["distanceAnalyzedM"] == 12_000.0
        assert body["secondsAnalyzed"] == 3_600.0
        # Cosmetic fields populated (above MIN_DISTANCE_M).
        assert body["persona"] != ""
        assert len(body["traits"]) == 6
        # 404 path.
        r404 = c.get("/api/sessions/missing_id/driver-profile")
        assert r404.status_code == 404


def test_evolution_window_length(app: FastAPI, client: TestClient) -> None:
    _seed(app, n_sessions=3)
    r = client.get("/api/driver/evolution?days=90")
    assert r.status_code == 200
    body = r.json()
    assert body["days"] == 90
    assert len(body["series"]) >= 2
    # Session cluster scatter present.
    assert len(body["sessionClusters"]) <= 32
