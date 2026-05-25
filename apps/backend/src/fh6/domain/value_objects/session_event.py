"""Historical per-session event record.

`SessionEvent` is the persistence-side counterpart to the in-flight
`Event` value object the `EventEmitter` produces for the live WS feed.
The live `Event` carries a wall-clock `at` — `SessionEvent` reduces
that to `at_s` (seconds since session start) so the highlight reel can
play back independently of when the session was recorded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SessionEvent:
    session_id: str
    at_s: float
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
