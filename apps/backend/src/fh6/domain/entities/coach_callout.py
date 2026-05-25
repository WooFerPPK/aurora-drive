from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from fh6.domain.value_objects.ids import SessionId


class CalloutPriority(StrEnum):
    INFO = "info"
    TIP = "tip"
    WARN = "warn"


@dataclass(slots=True)
class CoachCallout:
    id: str
    session_id: SessionId
    at_session_seconds: float
    priority: CalloutPriority
    lap_context: dict[str, Any]
    text: str
    cites: list[dict[str, Any]] = field(default_factory=list)
    model_version: str = ""
    voice: str = "friendly_codriver"
