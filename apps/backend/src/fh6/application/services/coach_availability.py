"""T093: CoachAvailabilityService (Clarification Q3).

Caches `claude --version` for ≤ 1 s. Surfaces `{available, reason, model}`
on `/api/coach/status` and in the `/ws/coach` hello message.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from fh6.domain.ports.llm_port import LLMAvailability, LLMPort


@dataclass(slots=True)
class _CachedAvailability:
    value: LLMAvailability
    checked_at: float


class CoachAvailabilityService:
    def __init__(
        self,
        llm: LLMPort,
        *,
        ttl_seconds: float = 1.0,
        clock: object = time.monotonic,
    ) -> None:
        self._llm = llm
        self._ttl = ttl_seconds
        self._clock = clock  # callable
        self._cached: _CachedAvailability | None = None
        self._lock = asyncio.Lock()

    def _now(self) -> float:
        return float(self._clock())  # type: ignore[operator]

    async def status(self) -> LLMAvailability:
        now = self._now()
        cached = self._cached
        if cached is not None and (now - cached.checked_at) <= self._ttl:
            return cached.value
        async with self._lock:
            # Double-check inside the lock.
            cached = self._cached
            if cached is not None and (self._now() - cached.checked_at) <= self._ttl:
                return cached.value
            try:
                fresh = await self._llm.availability()
            except Exception as exc:  # pragma: no cover — defensive
                fresh = LLMAvailability(
                    available=False, reason=f"availability_check_failed:{type(exc).__name__}"
                )
            self._cached = _CachedAvailability(value=fresh, checked_at=self._now())
            return fresh

    def invalidate(self) -> None:
        self._cached = None
