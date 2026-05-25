"""Base types for coach detectors. Each detector inspects the hot-cache
3 s rolling window and returns `Detection | None`."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from fh6.domain.entities.frame import DecodedFrame


@dataclass(slots=True)
class Detection:
    kind: str  # `oversteer | missed_upshift | off_track | late_throttle`
    priority: str  # `info | tip | warn`
    corner: str
    text_hint: str
    citations: list[dict[str, object]]


class Detector(Protocol):
    kind: str

    def detect(self, window: Sequence[DecodedFrame]) -> Detection | None: ...
