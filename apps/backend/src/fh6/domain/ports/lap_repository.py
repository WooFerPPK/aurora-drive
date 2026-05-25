from __future__ import annotations

from typing import Protocol

from fh6.domain.value_objects.completed_lap import CompletedLap
from fh6.domain.value_objects.ids import SessionId


class LapRepository(Protocol):
    async def upsert_lap(self, session_id: SessionId, lap: CompletedLap) -> None: ...

    async def list_laps_for_session(self, session_id: SessionId) -> list[CompletedLap]: ...

    async def min_lap_time_for_session(self, session_id: SessionId) -> float | None: ...
