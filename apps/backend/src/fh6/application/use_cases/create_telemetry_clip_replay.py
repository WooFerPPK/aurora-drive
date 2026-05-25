"""T115: build a `Replay(kind=telemetry_clip)` from a coach insight's
cited window."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fh6.domain.entities.replay import Replay, ReplayKind
from fh6.domain.ports.frame_store import FrameStore
from fh6.domain.ports.replay_repository import ReplayRepository
from fh6.domain.value_objects.ids import ReplayId, SessionId


class CreateTelemetryClipReplay:
    def __init__(
        self,
        *,
        frame_store: FrameStore,
        replay_repo: ReplayRepository,
    ) -> None:
        self._store = frame_store
        self._repo = replay_repo

    async def __call__(
        self,
        *,
        session_id: SessionId,
        from_s: float,
        to_s: float,
    ) -> Replay:
        projection = await self._store.read_projection(
            session_id,
            from_s=from_s,
            to_s=to_s,
            hz=30,
            fields=("speed", "throttle", "brake", "position"),
        )
        replay = Replay(
            id=ReplayId(f"tc_{uuid.uuid4().hex[:10]}"),
            kind=ReplayKind.TELEMETRY_CLIP,
            session_id=session_id,
            from_s=from_s,
            to_s=to_s,
            frames=projection.get("data") or [],
            annotations=[],
            created_at=datetime.now(UTC),
        )
        await self._repo.save(replay)
        return replay
