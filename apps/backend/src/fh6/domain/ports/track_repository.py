from __future__ import annotations

from typing import Protocol

from fh6.domain.entities.track import Track
from fh6.domain.value_objects.ids import TrackId


class TrackRepository(Protocol):
    async def get(self, track_id: TrackId) -> Track | None: ...

    async def save(self, track: Track) -> None: ...

    async def list_all(self) -> list[Track]: ...
