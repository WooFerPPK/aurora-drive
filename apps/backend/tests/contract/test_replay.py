"""T117: contract test for `/api/replay/:id` (API spec §9)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fh6.domain.entities.replay import Replay, ReplayKind
from fh6.domain.value_objects.ids import ReplayId, SessionId
from fh6.interfaces.rest.replay_router import router as replay_router
from tests.contract.fake_repos import InMemoryReplayRepository


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    a.state.replay_repo = InMemoryReplayRepository()
    a.include_router(replay_router, prefix="/api/replay")
    a.state.container = a.state

    return a


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_404_on_unknown(client: TestClient) -> None:
    r = client.get("/api/replay/unknown")
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "not_found"


def test_telemetry_clip_round_trip(app: FastAPI, client: TestClient) -> None:
    rep = Replay(
        id=ReplayId("tc_abc123"),
        kind=ReplayKind.TELEMETRY_CLIP,
        session_id=SessionId("s_1"),
        from_s=0.0,
        to_s=10.0,
        frames=[[0.0, 41.0, 0.8, 0.0]],
        created_at=datetime(2026, 5, 17, 12, 0, tzinfo=UTC),
    )
    app.state.replay_repo.replays["tc_abc123"] = rep
    r = client.get("/api/replay/tc_abc123")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "tc_abc123"
    assert body["kind"] == "telemetry_clip"
    assert body["sessionId"] == "s_1"
    assert body["from"] == 0.0
    assert body["to"] == 10.0
    assert body["frames"] == [[0.0, 41.0, 0.8, 0.0]]


def test_counter_factual_round_trip(app: FastAPI, client: TestClient) -> None:
    rep = Replay(
        id=ReplayId("cf_xyz789"),
        kind=ReplayKind.COUNTER_FACTUAL,
        session_id=SessionId("s_1"),
        from_s=5.0,
        to_s=12.0,
        tweaks=[{"kind": "brake_point_offset", "delta": -10.0}],
        created_at=datetime(2026, 5, 17, 12, 0, tzinfo=UTC),
    )
    app.state.replay_repo.replays["cf_xyz789"] = rep
    r = client.get("/api/replay/cf_xyz789")
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "counter_factual"
    assert body["tweaks"] == [{"kind": "brake_point_offset", "delta": -10.0}]
