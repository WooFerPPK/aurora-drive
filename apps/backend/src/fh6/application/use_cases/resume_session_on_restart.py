"""Clarification Q1: on service restart, resume the most recent in-flight
session IFF (a) timestamp gap between last persisted frame and the first
new packet is within the silence threshold AND (b) car identity matches.
Else finalize the prior session as `restart_finalize` and open new on
the next packet.

This is an explicit boot-time check rather than a fall-through behaviour
so the test for it is deterministic.

Rewind detection (30 s window): when the gap is < 30 s AND the same car
AND raceTimeS > 5 s, the new packet is treated as a rewind resumption
rather than a fresh session — the 30 s rewind window REPLACES the
silence-based heuristic for this specific case.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from fh6.application.services.session_manager import SessionManager, _derive_car_id
from fh6.domain.entities.frame import FrameRaw
from fh6.domain.entities.session import Session, SessionCloseReason
from fh6.domain.ports.session_repository import SessionRepository


class ResumeOutcome(StrEnum):
    NO_PRIOR_SESSION = "no_prior_session"
    RESUMED = "resumed"
    FINALIZED_PRIOR = "finalized_prior"


@dataclass(slots=True)
class ResumeResult:
    outcome: ResumeOutcome
    resumed: Session | None = None
    finalized: Session | None = None


class ResumeSessionOnRestart:
    def __init__(self, repo: SessionRepository, sm: SessionManager) -> None:
        self._repo = repo
        self._sm = sm

    async def apply(
        self,
        *,
        first_packet_at: datetime,
        first_packet_raw: FrameRaw,
        last_frame_at: datetime | None,
    ) -> ResumeResult:
        prior = await self._repo.latest_in_flight()
        if prior is None:
            return ResumeResult(outcome=ResumeOutcome.NO_PRIOR_SESSION)

        new_car_id = _derive_car_id(first_packet_raw)
        same_car = new_car_id == prior.car_id
        new_race_time = float(first_packet_raw.race.get("raceTimeS", 0.0) or 0.0)

        if last_frame_at is not None and same_car:
            gap_s = (first_packet_at - last_frame_at).total_seconds()
            # Rewind check: short wall gap + race still in meaningful
            # progress (> REWIND_MIN_RACE_TIME_S). This handles mid-race
            # rewinds that span a service restart (the 30 s window
            # REPLACES the silence-based heuristic for this case only).
            if (
                0.0 <= gap_s < SessionManager.REWIND_WINDOW_S
                and new_race_time > SessionManager.REWIND_MIN_RACE_TIME_S
            ):
                self._sm.adopt(prior, last_frame_at)
                return ResumeResult(outcome=ResumeOutcome.RESUMED, resumed=prior)

        # Existing silence-based resume: within silence threshold + same car.
        within_threshold = (
            last_frame_at is not None
            and (first_packet_at - last_frame_at) <= self._sm.silence_threshold
            and (first_packet_at - last_frame_at) >= timedelta(0)
        )
        if within_threshold and same_car and last_frame_at is not None:
            self._sm.adopt(prior, last_frame_at)
            return ResumeResult(outcome=ResumeOutcome.RESUMED, resumed=prior)

        # Otherwise finalize prior and let SessionManager open new on next frame.
        finalize_at = last_frame_at if last_frame_at is not None else prior.started_at
        prior.finalize(finalize_at, SessionCloseReason.RESTART_FINALIZE)
        await self._repo.save(prior)
        return ResumeResult(outcome=ResumeOutcome.FINALIZED_PRIOR, finalized=prior)
