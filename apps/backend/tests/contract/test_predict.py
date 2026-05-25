"""T142: contract test for `/api/predict` (API spec §6 + Clarification Q5)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from itertools import pairwise

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fh6.application.services.hot_cache import HotCache
from fh6.domain.entities.session import Session, SessionCloseReason, SessionType
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.interfaces.rest.predict_router import router as predict_router
from fh6.interfaces.rest.schemas.predict import LapPrediction, LapPredictionResponse
from tests.contract.fake_repos import (
    InMemoryCarRepository,
    InMemoryFrameStore,
    InMemoryReplayRepository,
    InMemorySessionRepository,
)


def _seed(repo: InMemorySessionRepository, sid: str = "s_pred") -> Session:
    s = Session(
        id=SessionId(sid),
        car_id=CarId("car_a"),
        type=SessionType.RACE,
        started_at=datetime(2026, 5, 17, 11, 0, tzinfo=UTC),
        ended_at=datetime(2026, 5, 17, 11, 30, tzinfo=UTC),
        duration_s=1800.0,
        lap_count=4,
        best_lap_s=68.4,
        top_speed_mps=92.0,
        closed_reason=SessionCloseReason.SHUTDOWN,
    )
    repo.sessions[sid] = s
    return s


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    a.state.car_repo = InMemoryCarRepository()
    a.state.session_repo = InMemorySessionRepository()
    a.state.frame_store = InMemoryFrameStore()
    a.state.replay_repo = InMemoryReplayRepository()
    a.state.hot_cache = HotCache()
    a.include_router(predict_router, prefix="/api/predict")
    a.state.container = a.state

    return a


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def _assert_envelope(body: dict[str, object]) -> None:
    for key in ("value", "confidence", "modelVersion", "inputs", "toleranceBand"):
        assert key in body, f"missing {key}: {body}"
    assert isinstance(body["confidence"], (int, float))
    assert 0.0 <= float(body["confidence"]) <= 1.0
    assert body["modelVersion"]
    assert isinstance(body["inputs"], list) and body["inputs"]


@pytest.mark.parametrize(
    "path",
    [
        # `lap` is intentionally excluded — after Task 1C.1/1C.2 it emits the
        # multi-lap shape and no longer fits the legacy single-value envelope.
        # `tireFailure` is intentionally excluded — Phase 2 backend rewrites
        # it as a per-corner shape with `failureAtLap` projection.
        # Dedicated tests below cover the new shapes.
        "finish",
        "crashRisk",
        "bestAchievableLap",
    ],
)
def test_get_predict_endpoint_shape(app: FastAPI, client: TestClient, path: str) -> None:
    _seed(app.state.session_repo)
    r = client.get(f"/api/predict/{path}?sessionId=s_pred")
    assert r.status_code == 200, r.text
    _assert_envelope(r.json())


def test_tire_failure_returns_per_corner_shape(app: FastAPI, client: TestClient) -> None:
    """The rich shape replaces the legacy envelope (api-contract §6)."""
    s = _seed(app.state.session_repo)
    r = client.get(f"/api/predict/tireFailure?sessionId={s.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "perCorner" in body
    for corner in ("fl", "fr", "rl", "rr"):
        assert corner in body["perCorner"]
        pc = body["perCorner"][corner]
        assert {"wear", "failureAtLap", "confidence"} <= set(pc.keys())
        assert 0.0 <= pc["wear"] <= 1.0
        assert 0.0 <= pc["confidence"] <= 1.0
        # failureAtLap may be None
    assert "limitingCorner" in body
    assert "modelVersion" in body


def test_predict_lap_returns_multi_lap_shape(app: FastAPI, client: TestClient) -> None:
    s = _seed(app.state.session_repo)
    r = client.get(f"/api/predict/lap?sessionId={s.id}&n=3")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "predictions" in body
    assert len(body["predictions"]) == 3
    for p in body["predictions"]:
        assert {"lap", "time_s", "lower_s", "upper_s", "confidence"} <= set(p)
        assert p["lower_s"] <= p["time_s"] <= p["upper_s"]
        assert 0.0 <= p["confidence"] <= 1.0
    assert "predictedAt" in body
    assert "modelVersion" in body
    assert "inputs" in body
    assert body["limiter"] is None
    # Numbering: base_lap = lap_count + 1 = 5, then 5,6,7 across k=0,1,2.
    assert [p["lap"] for p in body["predictions"]] == [5, 6, 7]


def test_predict_lap_confidence_decays(app: FastAPI, client: TestClient) -> None:
    """Net confidence must be monotone non-increasing across projections.

    Raw model confidence can rise as the seed window fills, so the router
    caps it at the first projection's raw value before applying the
    ``CONFIDENCE_DECAY_PER_LAP ** k`` multiplier. This makes "further-out
    projection = no more confident than a nearer one" actually true.
    """
    s = _seed(app.state.session_repo)
    r = client.get(f"/api/predict/lap?sessionId={s.id}&n=4")
    assert r.status_code == 200, r.text
    confs = [p["confidence"] for p in r.json()["predictions"]]
    for a, b in pairwise(confs):
        assert b <= a + 1e-9, f"confidence rose: {a} -> {b}"


def test_predict_lap_defaults_to_three_predictions(app: FastAPI, client: TestClient) -> None:
    s = _seed(app.state.session_repo)
    r = client.get(f"/api/predict/lap?sessionId={s.id}")
    assert r.status_code == 200, r.text
    assert len(r.json()["predictions"]) == 3


def test_predict_lap_cold_session_returns_empty_predictions(
    app: FastAPI, client: TestClient
) -> None:
    s = Session(
        id=SessionId("s_cold"),
        car_id=CarId("car_a"),
        type=SessionType.RACE,
        started_at=datetime(2026, 5, 17, 11, 0, tzinfo=UTC),
        ended_at=None,
        duration_s=0.0,
        lap_count=0,
        best_lap_s=None,
        top_speed_mps=0.0,
        closed_reason=None,
    )
    app.state.session_repo.sessions["s_cold"] = s
    r = client.get("/api/predict/lap?sessionId=s_cold")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["predictions"] == []
    # No hot-cache frame, so predictedAt falls back to 0.0.
    assert body["predictedAt"] == 0.0


def test_predict_lap_clamps_n_upper_bound(app: FastAPI, client: TestClient) -> None:
    _seed(app.state.session_repo)
    r = client.get("/api/predict/lap?sessionId=s_pred&n=15")
    assert r.status_code == 422


def test_predict_lap_clamps_n_lower_bound(app: FastAPI, client: TestClient) -> None:
    _seed(app.state.session_repo)
    r = client.get("/api/predict/lap?sessionId=s_pred&n=0")
    assert r.status_code == 422


def test_predict_404_on_unknown_session(client: TestClient) -> None:
    r = client.get("/api/predict/lap?sessionId=ghost")
    assert r.status_code == 404


def test_predict_fuel_endpoint_removed(app: FastAPI, client: TestClient) -> None:
    """FH6 pins engine.fuel at 1.0 — /api/predict/fuel must not exist.

    Even with a real seeded session, the route should be gone (FastAPI
    returns 404 ``{"detail": "Not Found"}`` for unmatched paths). This
    distinguishes "endpoint removed" from "session not found".
    """
    _seed(app.state.session_repo)
    r = client.get("/api/predict/fuel?sessionId=s_pred")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}


def test_what_if_happy_path(app: FastAPI, client: TestClient) -> None:
    _seed(app.state.session_repo)
    r = client.post(
        "/api/predict/whatIf",
        json={
            "sessionId": "s_pred",
            "from": 0.0,
            "to": 60.0,
            "tweaks": [{"kind": "brake_point_offset", "delta": 10.0}],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["replayId"].startswith("cf_")
    assert body["perTweak"]
    assert "lapDeltaS" in body
    assert body["modelVersion"]


def test_lap_prediction_response_shape() -> None:
    """The Pydantic model itself accepts the multi-lap shape per api-contract §6."""
    resp = LapPredictionResponse(
        predictions=[
            LapPrediction(lap=2, time_s=68.4, lower_s=67.6, upper_s=69.2, confidence=0.78),
            LapPrediction(lap=3, time_s=68.6, lower_s=67.5, upper_s=69.7, confidence=0.70),
        ],
        predictedAt=134.9,
        limiter=None,
        modelVersion="lap-residual-v0",
        inputs=["best_lap_s", "lap_count"],
    )
    data = resp.model_dump()
    assert len(data["predictions"]) == 2
    p = data["predictions"][0]
    assert {"lap", "time_s", "lower_s", "upper_s", "confidence"} <= set(p)
    assert p["lower_s"] <= p["time_s"] <= p["upper_s"]
    assert data["predictedAt"] == 134.9


@pytest.mark.parametrize(
    "kind",
    ["gear_ratio", "downforce", "tire_compound", "track_grip"],
)
def test_what_if_rejects_unknown_kinds(app: FastAPI, client: TestClient, kind: str) -> None:
    _seed(app.state.session_repo)
    r = client.post(
        "/api/predict/whatIf",
        json={
            "sessionId": "s_pred",
            "from": 0.0,
            "to": 30.0,
            "tweaks": [{"kind": kind, "delta": 1.0}],
        },
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["error"] == "validation_failed"
    assert "supported" in detail
    assert set(detail["supported"]) == {
        "brake_point_offset",
        "throttle_smoothness",
        "apex_offset",
        "shift_timing_offset",
    }
