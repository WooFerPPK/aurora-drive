"""T118: contract test for `/api/coach/ask` + insights (API spec §7B)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fh6.application.services.coach_availability import CoachAvailabilityService
from fh6.domain.entities.session import Session, SessionCloseReason, SessionType
from fh6.domain.ports.llm_port import LLMAvailability, LLMRequest
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.interfaces.rest.coach_router import router as coach_router
from fh6.interfaces.rest.replay_router import router as replay_router
from tests.contract.fake_repos import (
    InMemoryCarRepository,
    InMemoryCoachRepository,
    InMemoryFrameStore,
    InMemoryReplayRepository,
    InMemorySessionRepository,
)


class _StubLLM:
    async def availability(self) -> LLMAvailability:
        return LLMAvailability(available=True, model="stub")

    async def generate_callout(self, request: LLMRequest) -> str:  # pragma: no cover
        return "x"

    def stream_answer(self, request: LLMRequest) -> AsyncIterator[str]:
        async def _gen() -> AsyncIterator[str]:
            yield "Looking at the cited window "
            yield "(telemetry_window 0-10s in "
            yield f"sessionId={request.context['session_id']}). "
            yield "Brake 30 m earlier."

        return _gen()


def _seed_session(repo: InMemorySessionRepository, sid: str) -> Session:
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
    a.state.coach_repo = InMemoryCoachRepository()
    a.state.replay_repo = InMemoryReplayRepository()
    a.state.llm = _StubLLM()
    a.state.coach_availability = CoachAvailabilityService(_StubLLM())
    a.include_router(coach_router, prefix="/api/coach")
    a.include_router(replay_router, prefix="/api/replay")
    a.state.container = a.state

    return a


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_ask_streams_response_with_citation(app: FastAPI, client: TestClient) -> None:
    _seed_session(app.state.session_repo, "s_qa")
    with client.stream(
        "POST",
        "/api/coach/ask",
        json={"sessionId": "s_qa", "question": "Why am I slow into T3?"},
    ) as r:
        assert r.status_code == 200
        body = "".join(chunk for chunk in r.iter_text())
    assert "telemetry_window" in body
    assert "sessionId=s_qa" in body
    assert len(body) > 20  # streamed multiple chunks


def test_ask_404_on_unknown_session(client: TestClient) -> None:
    r = client.post(
        "/api/coach/ask",
        json={"sessionId": "ghost", "question": "?"},
    )
    assert r.status_code == 404


def test_insights_generate_and_list(app: FastAPI, client: TestClient) -> None:
    _seed_session(app.state.session_repo, "s_ins")
    r1 = client.post("/api/coach/insights/s_ins/generate")
    assert r1.status_code == 201
    assert r1.json()["generated"] >= 1

    r2 = client.get("/api/coach/insights?sessionId=s_ins")
    assert r2.status_code == 200
    body = r2.json()
    assert "insights" in body
    assert len(body["insights"]) >= 1
    card = body["insights"][0]
    for key in ("id", "sessionId", "priority", "title", "body", "tone"):
        assert key in card


def test_insight_dismiss_then_list_hides_it(app: FastAPI, client: TestClient) -> None:
    _seed_session(app.state.session_repo, "s_dis")
    client.post("/api/coach/insights/s_dis/generate")
    listed = client.get("/api/coach/insights?sessionId=s_dis").json()["insights"]
    assert listed
    insight_id = listed[0]["id"]
    r = client.post(f"/api/coach/insights/{insight_id}/dismiss")
    assert r.status_code == 204
    after = client.get("/api/coach/insights?sessionId=s_dis").json()["insights"]
    assert all(i["id"] != insight_id for i in after)


def test_insight_replay_returns_replay_id(app: FastAPI, client: TestClient) -> None:
    _seed_session(app.state.session_repo, "s_rep")
    client.post("/api/coach/insights/s_rep/generate")
    listed = client.get("/api/coach/insights?sessionId=s_rep").json()["insights"]
    insight_id = listed[0]["id"]
    r = client.post(f"/api/coach/insights/{insight_id}/replay")
    assert r.status_code == 200
    body = r.json()
    assert body["replayId"].startswith("tc_")
    # Replay row created.
    rep = client.get(f"/api/replay/{body['replayId']}")
    assert rep.status_code == 200
    assert rep.json()["kind"] == "telemetry_clip"
