"""Oversteer detector. Fires when rear-axle combinedSlip exceeds front-
axle by a sustained margin within the 3 s window."""

from __future__ import annotations

from collections.abc import Sequence

from fh6.domain.entities.frame import DecodedFrame
from fh6.infrastructure.coach.detectors.base import Detection


class OversteerDetector:
    kind = "oversteer"

    def __init__(self, *, rear_excess: float = 0.18, min_frames: int = 6) -> None:
        self._rear_excess = rear_excess
        self._min = min_frames

    def detect(self, window: Sequence[DecodedFrame]) -> Detection | None:
        if len(window) < self._min:
            return None
        recent = window[-self._min :]
        triggers = 0
        for f in recent:
            wheels = f.raw.wheels
            front = (wheels["fl"]["combinedSlip"] + wheels["fr"]["combinedSlip"]) / 2
            rear = (wheels["rl"]["combinedSlip"] + wheels["rr"]["combinedSlip"]) / 2
            if rear - front >= self._rear_excess:
                triggers += 1
        if triggers < self._min // 2:
            return None
        last = recent[-1]
        return Detection(
            kind=self.kind,
            priority="warn",
            corner=str(last.raw.race.get("lap", "?")),
            text_hint="Rear stepping out — ease steering, trail brake less.",
            citations=[
                {
                    "kind": "telemetry_window",
                    "sessionId": str(last.session_id) if last.session_id else "",
                    "from": recent[0].received_at.isoformat(),
                    "to": last.received_at.isoformat(),
                    "fields": ["wheels.rl.combinedSlip", "wheels.rr.combinedSlip"],
                }
            ],
        )
