"""Late-throttle detector. Fires when, after a sustained brake event,
throttle re-application is delayed (throttle stays < 0.3 for too long
after brake releases). Coarse but useful as a co-driver tip."""

from __future__ import annotations

from collections.abc import Sequence

from fh6.domain.entities.frame import DecodedFrame
from fh6.infrastructure.coach.detectors.base import Detection


class LateThrottleDetector:
    kind = "late_throttle"

    def __init__(
        self,
        *,
        brake_release_threshold: float = 0.05,
        throttle_late_threshold: float = 0.3,
        post_release_min_frames: int = 30,  # ~0.5 s @ 60 Hz
    ) -> None:
        self._brake_release = brake_release_threshold
        self._throttle_late = throttle_late_threshold
        self._post_release_min = post_release_min_frames

    def detect(self, window: Sequence[DecodedFrame]) -> Detection | None:
        if len(window) < self._post_release_min + 10:
            return None
        recent = list(window)
        # Look for a brake-release transition.
        release_idx: int | None = None
        for i in range(1, len(recent)):
            if (
                recent[i - 1].raw.inputs.get("brake", 0.0) >= 0.3
                and recent[i].raw.inputs.get("brake", 0.0) < self._brake_release
            ):
                release_idx = i
        if release_idx is None:
            return None
        tail = recent[release_idx : release_idx + self._post_release_min]
        if len(tail) < self._post_release_min:
            return None
        if any(f.raw.inputs.get("throttle", 0.0) >= self._throttle_late for f in tail):
            return None  # throttle was applied → not late
        last = tail[-1]
        return Detection(
            kind=self.kind,
            priority="tip",
            corner=str(last.raw.race.get("lap", "?")),
            text_hint="Get back on throttle earlier on exit — you're coasting too long.",
            citations=[
                {
                    "kind": "telemetry_window",
                    "sessionId": str(last.session_id) if last.session_id else "",
                    "from": tail[0].received_at.isoformat(),
                    "to": last.received_at.isoformat(),
                    "fields": ["inputs.brake", "inputs.throttle"],
                }
            ],
        )
