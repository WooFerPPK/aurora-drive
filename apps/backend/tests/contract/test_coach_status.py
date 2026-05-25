"""T095: contract test for `/api/coach/status` (Clarification Q3).

Asserts the documented shape AND that non-coach endpoints stay 200
when the CLI is unavailable.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fh6.application.services.coach_availability import CoachAvailabilityService
from fh6.domain.ports.llm_port import LLMAvailability, LLMRequest
from fh6.interfaces.rest.coach_router import router as coach_router
from fh6.interfaces.rest.sessions_router import router as sessions_router
from tests.contract.fake_repos import (
    InMemoryCarRepository,
    InMemoryCoachRepository,
    InMemoryFrameStore,
    InMemorySessionRepository,
)


class _UnavailableLLM:
    async def availability(self) -> LLMAvailability:
        return LLMAvailability(available=False, reason="claude_cli_not_installed")

    async def generate_callout(self, request: LLMRequest) -> str:  # pragma: no cover
        raise RuntimeError("unavailable")

    def stream_answer(self, request: LLMRequest) -> AsyncIterator[str]:  # pragma: no cover
        async def _gen() -> AsyncIterator[str]:
            yield ""

        return _gen()


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    a.state.car_repo = InMemoryCarRepository()
    a.state.session_repo = InMemorySessionRepository()
    a.state.frame_store = InMemoryFrameStore()
    a.state.coach_repo = InMemoryCoachRepository()
    a.state.coach_availability = CoachAvailabilityService(_UnavailableLLM())
    a.include_router(sessions_router, prefix="/api/sessions")
    a.include_router(coach_router, prefix="/api/coach")
    a.state.container = a.state

    return a


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_status_when_unavailable(client: TestClient) -> None:
    r = client.get("/api/coach/status")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert body["reason"] == "claude_cli_not_installed"


def test_non_coach_endpoints_unaffected(client: TestClient) -> None:
    r = client.get("/api/sessions")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
