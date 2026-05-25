"""T099: CalloutEngine.

Separate consumer task on the frame stream. On detector fire + cool-
down allow, calls the LLM port for callout text, persists a
`CoachCallout`, and emits the payload to the coach WebSocket broker.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable, Sequence

from fh6.application.services.coach_availability import CoachAvailabilityService
from fh6.application.services.hot_cache import HotCache
from fh6.domain.entities.coach_callout import CalloutPriority, CoachCallout
from fh6.domain.entities.frame import DecodedFrame
from fh6.domain.ports.coach_repository import CoachRepository
from fh6.domain.ports.llm_port import LLMPort, LLMRequest
from fh6.infrastructure.coach.cooldown_policy import CooldownPolicy
from fh6.infrastructure.coach.detectors.base import Detection, Detector
from fh6.infrastructure.logging import get_logger

log = get_logger(__name__)


CalloutSink = Callable[[CoachCallout], Awaitable[None]]


class CalloutEngine:
    def __init__(
        self,
        *,
        detectors: Sequence[Detector],
        cooldown: CooldownPolicy,
        llm: LLMPort,
        coach_repo: CoachRepository,
        hot_cache: HotCache,
        availability: CoachAvailabilityService,
        sink: CalloutSink,
        clock: Callable[[], float] = time.monotonic,
        min_priority: CalloutPriority = CalloutPriority.TIP,
        enabled: bool = True,
    ) -> None:
        self._detectors = list(detectors)
        self._cooldown = cooldown
        self._llm = llm
        self._repo = coach_repo
        self._cache = hot_cache
        self._availability = availability
        self._sink = sink
        self._clock = clock
        self._min_priority = min_priority
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = value

    def set_min_priority(self, p: CalloutPriority) -> None:
        self._min_priority = p

    async def on_frame(self, frame: DecodedFrame) -> None:
        if not self._enabled or frame.session_id is None:
            return
        availability = await self._availability.status()
        if not availability.available:
            return
        window = self._cache.window_for(frame.session_id, frame.car_id)
        if len(window) < 3:
            return
        for det in self._detectors:
            try:
                detection = det.detect(window)
            except Exception:  # pragma: no cover — defensive
                log.exception("detector_error", kind=det.kind)
                continue
            if detection is None:
                continue
            priority = CalloutPriority(detection.priority)
            if _rank(priority) < _rank(self._min_priority):
                continue
            now = self._clock()
            lap = int(frame.raw.race.get("lap", 0))
            decision = self._cooldown.evaluate(
                kind=detection.kind,
                corner=detection.corner,
                priority=priority,
                lap=lap,
                now=now,
            )
            if not decision.allowed:
                continue
            try:
                text = await self._llm.generate_callout(
                    LLMRequest(
                        template_name="live_callout",
                        context=_context(detection, frame),
                    )
                )
            except Exception:
                log.exception("llm_callout_failed", kind=detection.kind)
                continue
            callout = CoachCallout(
                id=f"c_{uuid.uuid4().hex[:10]}",
                session_id=frame.session_id,
                at_session_seconds=_session_seconds(frame),
                priority=priority,
                lap_context={"lap": lap, "corner": detection.corner},
                text=text.strip(),
                cites=detection.citations,
                model_version=availability.model or "claude-cli",
            )
            self._cooldown.record(
                kind=detection.kind,
                corner=detection.corner,
                priority=priority,
                lap=lap,
                now=now,
            )
            await self._repo.save_callout(callout)
            await self._sink(callout)


def _rank(p: CalloutPriority) -> int:
    return {CalloutPriority.INFO: 0, CalloutPriority.TIP: 1, CalloutPriority.WARN: 2}[p]


def _session_seconds(frame: DecodedFrame) -> float:
    race_time = float(frame.raw.race.get("raceTimeS", 0.0) or 0.0)
    return race_time


def _context(detection: Detection, frame: DecodedFrame) -> dict[str, object]:
    wheels = frame.raw.wheels
    avg_slip = sum(w["combinedSlip"] for w in wheels.values()) / 4
    return {
        "detector_kind": detection.kind,
        "lap": frame.raw.race.get("lap", "?"),
        "corner": detection.corner,
        "speed_mps": frame.raw.motion.get("speed_mps", 0.0),
        "throttle": frame.raw.inputs.get("throttle", 0.0),
        "brake": frame.raw.inputs.get("brake", 0.0),
        "slip": round(avg_slip, 3),
        "recent_window_summary": detection.text_hint,
    }


__all__ = ["CalloutEngine", "CalloutSink"]
