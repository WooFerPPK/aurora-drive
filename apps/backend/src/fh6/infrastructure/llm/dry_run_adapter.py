"""T091: DryRunLLMAdapter.

Returns canned responses for tests so the coach pipeline can be
exercised without the `claude` CLI present on the machine. Activated
by `llm.dryRun=true` (settings) or `FH6_LLM_DRY_RUN=true`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fh6.domain.ports.llm_port import LLMAvailability, LLMPort, LLMRequest


class DryRunLLMAdapter(LLMPort):
    def __init__(self, *, model_name: str = "dry-run-stub") -> None:
        self._model = model_name

    async def availability(self) -> LLMAvailability:
        return LLMAvailability(available=True, reason="dry-run", model=self._model)

    async def generate_callout(self, request: LLMRequest) -> str:
        kind = request.context.get("detector_kind", "general")
        corner = request.context.get("corner", "?")
        return f"[dry-run] {kind} at {corner}: trail brake later, roll on throttle smoothly."

    def stream_answer(self, request: LLMRequest) -> AsyncIterator[str]:
        async def _gen() -> AsyncIterator[str]:
            chunks = [
                "[dry-run] Looking at the cited windows — ",
                "the data shows late braking before T3 (",
                "cite: telemetry_window 12.4-14.1s, fields=[brake,speed]). ",
                "Try braking 30 m earlier next lap.",
            ]
            for c in chunks:
                yield c

        return _gen()
