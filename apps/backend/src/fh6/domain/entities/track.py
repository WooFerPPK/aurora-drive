from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from fh6.domain.value_objects.ids import TrackId


@dataclass(slots=True)
class Track:
    id: TrackId
    display_name: str
    inferred: bool = True
    confirmed_name: str | None = None
    confirmed_at: datetime | None = None
    outline: list[tuple[float, float]] = field(default_factory=list)
    corners: list[dict[str, object]] = field(default_factory=list)
    created_at: datetime | None = None
