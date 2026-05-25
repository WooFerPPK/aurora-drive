from __future__ import annotations

from typing import Protocol

from fh6.domain.entities.coach_callout import CoachCallout
from fh6.domain.entities.coach_insight import CoachInsight
from fh6.domain.value_objects.ids import SessionId


class CoachRepository(Protocol):
    async def save_callout(self, callout: CoachCallout) -> None: ...

    async def list_callouts(self, session_id: SessionId) -> list[CoachCallout]: ...

    async def save_insight(self, insight: CoachInsight) -> None: ...

    async def list_insights(self, session_id: SessionId) -> list[CoachInsight]: ...

    async def get_insight(self, insight_id: str) -> CoachInsight | None: ...

    async def dismiss_insight(self, insight_id: str) -> bool: ...
