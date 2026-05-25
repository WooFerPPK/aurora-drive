from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fh6.domain.value_objects.ids import CarId, TrackId


@dataclass(slots=True)
class Mistake:
    car_id: CarId
    track_id: TrackId
    pos: list[float]
    kind: str
    count: int = 1
    corner: str | None = None
    last_observed_at: datetime | None = None
