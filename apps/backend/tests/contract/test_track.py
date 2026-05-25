"""T079: contract test for `/api/track` (API spec §8)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fh6.domain.entities.car import Car
from fh6.domain.entities.session import Session, SessionCloseReason, SessionType
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.interfaces.rest.track_router import router as track_router
from tests.contract.fake_repos import (
    InMemoryCarRepository,
    InMemoryFrameStore,
    InMemorySessionRepository,
)


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    a.state.car_repo = InMemoryCarRepository()
    a.state.session_repo = InMemorySessionRepository()
    a.state.frame_store = InMemoryFrameStore()
    a.include_router(track_router, prefix="/api/track")
    a.state.container = a.state

    return a


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def _seed_session(app: FastAPI) -> Session:
    s = Session(
        id=SessionId("s_track_1"),
        car_id=CarId("car_a"),
        type=SessionType.RACE,
        started_at=datetime(2026, 5, 17, 11, 0, tzinfo=UTC),
        ended_at=datetime(2026, 5, 17, 11, 30, tzinfo=UTC),
        duration_s=1800.0,
        lap_count=3,
        closed_reason=SessionCloseReason.SHUTDOWN,
    )
    app.state.session_repo.sessions[str(s.id)] = s
    app.state.car_repo.cars["car_a"] = Car(
        id=CarId("car_a"),
        display_name="car a",
        short_name="cara",
        car_ordinal=1,
        car_class="A",
        performance_index=800,
        drivetrain="AWD",
        car_group=0,
    )
    return s


def test_track_current_inferred_true(client: TestClient) -> None:
    r = client.get("/api/track/current")
    assert r.status_code == 200
    body = r.json()
    assert body["inferred"] is True  # FR-019
    assert "trackId" in body
    assert "outline" in body
    assert "corners" in body


def test_optimal_line_returns_shape(app: FastAPI, client: TestClient) -> None:
    _seed_session(app)
    r = client.get("/api/track/optimal-line?sessionId=s_track_1")
    assert r.status_code == 200
    body = r.json()
    assert body["sessionId"] == "s_track_1"
    assert "optimalLine" in body
    assert "yourLine" in body
    assert "incidents" in body
    assert "sectorDeltas" in body


def test_optimal_line_404_unknown_session(client: TestClient) -> None:
    r = client.get("/api/track/optimal-line?sessionId=does_not_exist")
    assert r.status_code == 404


def test_mistakes_returns_documented_shape(app: FastAPI, client: TestClient) -> None:
    _seed_session(app)
    r = client.get("/api/track/mistakes?carId=car_a")
    assert r.status_code == 200
    body = r.json()
    assert body["carId"] == "car_a"
    assert "buckets" in body
    assert "breakdown" in body
    assert "trend" in body
