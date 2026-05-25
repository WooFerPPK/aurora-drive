from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from fh6.domain.value_objects.ids import ReplayId, SessionId

# Clarification Q5: closed set of supported what-if tweak kinds.
WHAT_IF_TWEAK_KINDS: frozenset[str] = frozenset(
    {
        "brake_point_offset",
        "throttle_smoothness",
        "apex_offset",
        "shift_timing_offset",
    }
)


class ReplayKind(StrEnum):
    COUNTER_FACTUAL = "counter_factual"
    TELEMETRY_CLIP = "telemetry_clip"


@dataclass(slots=True)
class Replay:
    id: ReplayId
    kind: ReplayKind
    session_id: SessionId
    from_s: float
    to_s: float
    frames: list[dict[str, object]] = field(default_factory=list)
    annotations: list[dict[str, object]] = field(default_factory=list)
    tweaks: list[dict[str, object]] | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.kind == ReplayKind.COUNTER_FACTUAL:
            if not self.tweaks:
                raise ValueError("counter_factual replay requires tweaks")
            for t in self.tweaks:
                kind = t.get("kind")
                if kind not in WHAT_IF_TWEAK_KINDS:
                    raise ValueError(
                        f"unsupported tweak kind: {kind!r}; "
                        f"supported: {sorted(WHAT_IF_TWEAK_KINDS)}"
                    )
