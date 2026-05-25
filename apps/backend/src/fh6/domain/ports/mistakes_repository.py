from __future__ import annotations

from typing import Protocol

from fh6.domain.entities.mistake import Mistake
from fh6.domain.value_objects.ids import CarId, TrackId


class MistakesRepository(Protocol):
    async def save(self, mistake: Mistake) -> None: ...

    async def list_for_car_track(self, car_id: CarId, track_id: TrackId) -> list[Mistake]: ...
