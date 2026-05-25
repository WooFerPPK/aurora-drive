from __future__ import annotations

from typing import Protocol

from fh6.domain.entities.car import Car
from fh6.domain.value_objects.ids import CarId


class CarRepository(Protocol):
    async def upsert(self, car: Car) -> None: ...

    async def get(self, car_id: CarId) -> Car | None: ...

    async def list_all(self) -> list[Car]: ...

    async def delete_all_sessions(self, car_id: CarId) -> int: ...

    async def delete(self, car_id: CarId) -> bool: ...

    async def delete_all(self) -> int: ...

    async def rename_by_ordinal(self, ordinal: int, *, display_name: str, short_name: str) -> int:
        """Crowdsourcing path: stamp a user-supplied name onto every
        Car row sharing this ordinal. Returns the number of rows
        updated (0 if no car with that ordinal exists yet)."""
        ...
