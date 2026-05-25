from __future__ import annotations

from typing import Protocol

from fh6.domain.entities.driver_profile import DriverProfile


class DriverRepository(Protocol):
    async def get(self) -> DriverProfile: ...

    async def save(self, profile: DriverProfile) -> None: ...
