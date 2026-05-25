"""Missed-upshift detector. Fires when `rpm` stays > 95% of `maxRpm`
for a sustained window without a gear up-change."""

from __future__ import annotations

from collections.abc import Sequence

from fh6.domain.entities.frame import DecodedFrame
from fh6.infrastructure.coach.detectors.base import Detection


class MissedUpshiftDetector:
    kind = "missed_upshift"

    def __init__(self, *, rpm_ratio_min: float = 0.95, min_frames: int = 10) -> None:
        self._ratio = rpm_ratio_min
        self._min = min_frames

    def detect(self, window: Sequence[DecodedFrame]) -> Detection | None:
        if len(window) < self._min:
            return None
        recent = window[-self._min :]
        gears = [f.raw.drivetrain.get("gear", 0) for f in recent]
        if len(set(gears)) > 1:
            return None  # gear changed within window — no miss
        for f in recent:
            rpm = float(f.raw.engine.get("rpm", 0.0))
            mx = float(f.raw.engine.get("maxRpm", rpm or 1.0))
            if mx <= 0 or rpm / mx < self._ratio:
                return None
        last = recent[-1]
        return Detection(
            kind=self.kind,
            priority="tip",
            corner=str(last.raw.race.get("lap", "?")),
            text_hint="You're holding redline — shift up to keep the powerband.",
            citations=[
                {
                    "kind": "telemetry_window",
                    "sessionId": str(last.session_id) if last.session_id else "",
                    "from": recent[0].received_at.isoformat(),
                    "to": last.received_at.isoformat(),
                    "fields": ["engine.rpm", "drivetrain.gear"],
                }
            ],
        )
