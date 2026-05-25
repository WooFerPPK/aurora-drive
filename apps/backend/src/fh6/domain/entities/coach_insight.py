from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from fh6.domain.value_objects.ids import ReplayId, SessionId


@dataclass(slots=True)
class CoachInsight:
    id: str
    session_id: SessionId
    priority: str  # high|medium|low
    title: str
    body: str
    tone: str  # tip|warn|info
    actions: list[str] = field(default_factory=list)
    delta_if_fixed_s: float | None = None
    dismissed_at: datetime | None = None
    replay_id: ReplayId | None = None
