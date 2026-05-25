"""Off-track detector. Fires when ≥ 2 wheels report `inPuddle=1` and
combinedSlip > 0.3 for several frames (a coarse on-grass proxy)."""

from __future__ import annotations

from collections.abc import Sequence

from fh6.domain.entities.frame import DecodedFrame
from fh6.infrastructure.coach.detectors.base import Detection


class OffTrackDetector:
    kind = "off_track"

    def __init__(self, *, min_frames: int = 4, slip_min: float = 0.30) -> None:
        self._min = min_frames
        self._slip = slip_min

    def detect(self, window: Sequence[DecodedFrame]) -> Detection | None:
        if len(window) < self._min:
            return None
        recent = window[-self._min :]
        for f in recent:
            wheels = f.raw.wheels
            puddled = sum(int(w["inPuddle"]) for w in wheels.values())
            avg_slip = sum(w["combinedSlip"] for w in wheels.values()) / 4
            if puddled < 2 or avg_slip < self._slip:
                return None
        last = recent[-1]
        return Detection(
            kind=self.kind,
            priority="warn",
            corner=str(last.raw.race.get("lap", "?")),
            text_hint="Off-track — straighten, lift, then reapply gently.",
            citations=[
                {
                    "kind": "telemetry_window",
                    "sessionId": str(last.session_id) if last.session_id else "",
                    "from": recent[0].received_at.isoformat(),
                    "to": last.received_at.isoformat(),
                    "fields": [
                        "wheels.fl.inPuddle",
                        "wheels.fr.inPuddle",
                        "wheels.rl.inPuddle",
                        "wheels.rr.inPuddle",
                    ],
                }
            ],
        )
