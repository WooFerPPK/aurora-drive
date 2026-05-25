"""T101: unit test for CoachAvailabilityService (Clarification Q3)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from fh6.application.services.coach_availability import CoachAvailabilityService
from fh6.domain.ports.llm_port import LLMAvailability, LLMRequest


class FakeLLM:
    def __init__(self) -> None:
        self.calls = 0
        self.value = LLMAvailability(available=True, reason=None, model="fake-1.0")

    async def availability(self) -> LLMAvailability:
        self.calls += 1
        return self.value

    async def generate_callout(self, request: LLMRequest) -> str:  # pragma: no cover
        return "fake"

    def stream_answer(self, request: LLMRequest) -> AsyncIterator[str]:  # pragma: no cover
        async def _gen() -> AsyncIterator[str]:
            yield "x"

        return _gen()


@pytest.mark.asyncio
async def test_ttl_caches_within_1_second() -> None:
    clock = [0.0]
    llm = FakeLLM()
    svc = CoachAvailabilityService(llm, ttl_seconds=1.0, clock=lambda: clock[0])
    assert (await svc.status()).available
    assert llm.calls == 1
    clock[0] = 0.5
    await svc.status()
    assert llm.calls == 1  # cached


@pytest.mark.asyncio
async def test_recheck_after_ttl_expiry() -> None:
    clock = [0.0]
    llm = FakeLLM()
    svc = CoachAvailabilityService(llm, ttl_seconds=1.0, clock=lambda: clock[0])
    await svc.status()
    clock[0] = 1.5
    await svc.status()
    assert llm.calls == 2


@pytest.mark.asyncio
async def test_cli_missing_fallback() -> None:
    llm = FakeLLM()
    llm.value = LLMAvailability(available=False, reason="claude_cli_not_installed")
    svc = CoachAvailabilityService(llm, ttl_seconds=1.0)
    av = await svc.status()
    assert not av.available
    assert av.reason == "claude_cli_not_installed"
