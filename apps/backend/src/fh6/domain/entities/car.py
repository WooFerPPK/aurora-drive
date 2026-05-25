from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fh6.domain.value_objects.ids import CarId


@dataclass(slots=True)
class Car:
    id: CarId
    display_name: str
    short_name: str
    car_ordinal: int
    car_class: str
    performance_index: int
    drivetrain: str
    car_group: int
    car_group_label: str | None = None
    last_seen_at: datetime | None = None
    session_count: int = 0
    total_seconds_driven: float = 0.0
