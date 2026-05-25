from __future__ import annotations

from typing import Protocol

from fh6.domain.entities.prediction import Prediction, PredictionKind
from fh6.domain.value_objects.ids import SessionId


class PredictionRepository(Protocol):
    async def save(self, prediction: Prediction) -> None: ...

    async def list_for_session(
        self, session_id: SessionId, *, kind: PredictionKind | None = None
    ) -> list[Prediction]: ...
