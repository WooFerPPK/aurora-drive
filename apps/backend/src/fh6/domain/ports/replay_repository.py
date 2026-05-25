from __future__ import annotations

from typing import Protocol

from fh6.domain.entities.replay import Replay
from fh6.domain.value_objects.ids import ReplayId


class ReplayRepository(Protocol):
    async def save(self, replay: Replay) -> None: ...

    async def get(self, replay_id: ReplayId) -> Replay | None: ...
