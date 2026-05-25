from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class LLMRequest:
    template_name: str
    context: dict[str, object]
    max_output_tokens: int = 1024


@dataclass(slots=True)
class LLMAvailability:
    available: bool
    reason: str | None = None
    model: str | None = None


class LLMPort(Protocol):
    """Constitution Principle III: only implementor is the Claude headless
    subprocess adapter or the dry-run adapter for tests. Domain code never
    imports `subprocess` or any Anthropic SDK directly."""

    async def availability(self) -> LLMAvailability: ...

    async def generate_callout(self, request: LLMRequest) -> str: ...

    def stream_answer(self, request: LLMRequest) -> AsyncIterator[str]: ...
