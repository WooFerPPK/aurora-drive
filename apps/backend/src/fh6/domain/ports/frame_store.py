from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal, Protocol

from fh6.domain.entities.frame import DecodedFrame
from fh6.domain.value_objects.frame_position import FramePositionSnapshot
from fh6.domain.value_objects.ids import CarId, SessionId


class FrameStore(Protocol):
    async def append(self, frame: DecodedFrame) -> None: ...

    async def append_batch(self, frames: Sequence[DecodedFrame]) -> None: ...

    async def read_projection(
        self,
        session_id: SessionId,
        *,
        from_s: float | None = None,
        to_s: float | None = None,
        hz: Literal[10, 30, 60] = 30,
        fields: Sequence[str] | None = None,
    ) -> dict[str, Any]: ...

    async def last_frame_time(self, session_id: SessionId) -> datetime | None: ...

    async def bytes_used_by_car(self, car_id: CarId) -> int: ...

    async def delete_session(self, session_id: SessionId) -> int: ...

    async def read_last_position_snapshot(
        self, session_id: SessionId
    ) -> FramePositionSnapshot | None:
        """Return the latest persisted frame's position + yaw, or None
        if no frames are persisted for this session. Used by the rewind
        detector when re-arming after a `SessionManager.adopt()`."""
        ...

    async def read_position_track(self, session_id: SessionId) -> Sequence[FramePositionSnapshot]:
        """Return all persisted frames' (time, position, yaw) for the
        session, ordered by time ascending. Used by the rewind detector
        to scan for the latest matching position on a teleport."""
        ...

    async def delete_frames_in_range(
        self,
        session_id: SessionId,
        *,
        after: datetime,
        before: datetime,
    ) -> int:
        """Delete frames with `time > after AND time < before` (both
        bounds exclusive) for the session, in a single transaction.
        Returns the number of rows deleted."""
        ...
