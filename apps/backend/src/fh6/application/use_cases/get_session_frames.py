"""T074: GET /api/sessions/:id/frames projection.

Reads from the right table per `hz`:
- hz=10 → `frames_10hz` continuous aggregate
- hz=30 → `frames_30hz` continuous aggregate
- hz=60 → source `frames` hypertable

The `fields=` query param projects to a deterministic column order.
Source-rate persistence is never decimated at write time (constitution
Principle VIII); decimation is read-time only.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from fh6.domain.ports.frame_store import FrameStore
from fh6.domain.value_objects.ids import SessionId

DEFAULT_FIELDS: tuple[str, ...] = ("speed", "throttle", "brake", "position")
# Replay / scrubber driving fields. `rpm` and `gear` cover the dash
# widgets (RpmDial, RpmTape, SpeedDial). The widget-redesign expansion
# (currentLapS/lastLapS/bestLapS, gripBudget, acceleration, tireTemp)
# unblocks LapTimer, GripBudget, GMeter, and TireHeatmap during replay.
SUPPORTED_FIELDS: frozenset[str] = frozenset(DEFAULT_FIELDS) | {
    "rpm",
    "gear",
    "currentLapS",
    "lastLapS",
    "bestLapS",
    "gripBudget",
    "acceleration",
    "tireTemp",
}
SUPPORTED_HZ: frozenset[int] = frozenset({10, 30, 60})


class UnsupportedHz(ValueError):
    def __init__(self, hz: int) -> None:
        super().__init__(f"hz={hz} not in {sorted(SUPPORTED_HZ)}")
        self.hz = hz


class UnsupportedField(ValueError):
    def __init__(self, field: str) -> None:
        super().__init__(f"field={field!r} not in {sorted(SUPPORTED_FIELDS)}")
        self.field = field


class GetSessionFrames:
    def __init__(self, frame_store: FrameStore) -> None:
        self._store = frame_store

    @staticmethod
    def parse_fields(raw: str | None) -> list[str]:
        if raw is None or not raw.strip():
            return list(DEFAULT_FIELDS)
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        for p in parts:
            if p not in SUPPORTED_FIELDS:
                raise UnsupportedField(p)
        return parts

    @staticmethod
    def parse_hz(raw: int) -> Literal[10, 30, 60]:
        if raw not in SUPPORTED_HZ:
            raise UnsupportedHz(raw)
        return raw  # type: ignore[return-value]

    async def __call__(
        self,
        session_id: SessionId,
        *,
        hz: Literal[10, 30, 60] = 30,
        fields: Sequence[str] | None = None,
        from_s: float | None = None,
        to_s: float | None = None,
    ) -> dict[str, object]:
        return await self._store.read_projection(
            session_id,
            from_s=from_s,
            to_s=to_s,
            hz=hz,
            fields=tuple(fields) if fields else None,
        )
