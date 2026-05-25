"""End-to-end: rewind that spans a service restart.

Sequence:
1. Session S1 is opened in "service 1"; frames are recorded driving
   from x=0 to x=200 (raceTimeS = 0..20).
2. "Service 1" stops — frames are in the store, session S1 is still
   in_flight (ended_at=None).
3. "Service 2" boots. The first new packet looks like a rewind:
   1 s wall gap, same car, raceTimeS=10 (well above the 5 s floor).
   `ResumeSessionOnRestart.apply` detects this and calls
   `sm.adopt(S1, last_frame_at)`. The adopt listener (sync) marks the
   detector as "pending baseline reload."
4. The first new frame is at x=20 — teleport from the x=200 baseline.
   The detector's on_frame lazily loads the baseline, classifies the
   frame as a teleport, scans history, finds the x=20 match, and
   truncates frames at x > 20.
5. Assertion: max(x) in the store is 20.
"""

from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime, timedelta

import pytest

from fh6.application.services.hot_cache import HotCache
from fh6.application.services.rewind_detector import RewindDetector
from fh6.application.services.session_manager import SessionManager
from fh6.application.use_cases.ingest_frame import IngestFrame
from fh6.application.use_cases.resume_session_on_restart import ResumeSessionOnRestart
from tests.contract.fake_repos import (
    InMemoryCarRepository,
    InMemoryFrameStore,
    InMemorySessionRepository,
)
from tests.integration.test_rewind_detector_e2e import _raw  # reuse the helper


def _detector(store: InMemoryFrameStore, hot: HotCache) -> RewindDetector:
    return RewindDetector(
        frame_store=store,
        continuity_threshold_m=20.0,
        match_tolerance_m=5.0,
        yaw_tolerance_rad=math.pi / 2,
        pause_floor=timedelta(milliseconds=250),
        hot_cache=hot,
    )


def _ingest(
    sm: SessionManager,
    store: InMemoryFrameStore,
    hot: HotCache,
    repo: InMemorySessionRepository,
    detector: RewindDetector,
) -> IngestFrame:
    queue: asyncio.Queue = asyncio.Queue()
    return IngestFrame(
        queue=queue,
        session_manager=sm,
        session_repository=repo,
        frame_store=store,
        hot_cache=hot,
        car_repository=InMemoryCarRepository(),
        lap_repository=None,
        tire_wear_model=None,
        rewind_detector=detector,
    )


@pytest.mark.asyncio
async def test_restart_rewind_truncates_post_match_frames() -> None:
    # ---- Phase 1: First service lifetime ----
    sm1 = SessionManager(silence_seconds=60.0)
    store = InMemoryFrameStore()
    repo = InMemorySessionRepository()
    hot1 = HotCache()
    detector1 = _detector(store, hot1)
    sm1.add_adopt_listener(detector1.on_adopt)
    ingest1 = _ingest(sm1, store, hot1, repo, detector1)

    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(21):  # x = 0..200 in steps of 10
        raw = _raw(x=float(i * 10), ts_ms=i * 33)
        # is_race_on=True (default) and raceTimeS growing
        raw.race["raceTimeS"] = float(i)
        await ingest1._handle_one(raw, t0 + timedelta(milliseconds=33 * i))

    sessions = await repo.list_all()
    assert len(sessions) == 1
    s1 = sessions[0]
    assert s1.ended_at is None
    last_frame_at = t0 + timedelta(milliseconds=33 * 20)

    # ---- Phase 2: Second service lifetime ----
    sm2 = SessionManager(silence_seconds=60.0)
    hot2 = HotCache()
    detector2 = _detector(store, hot2)
    sm2.add_adopt_listener(detector2.on_adopt)
    resume = ResumeSessionOnRestart(repo=repo, sm=sm2)

    # First packet at x=20 (matches historical frame i=2). 1 s wall gap,
    # raceTimeS=10 (above 5 s floor, below pre-restart peak of 20).
    first_raw = _raw(x=20.0, ts_ms=33 * 30)
    first_raw.race["raceTimeS"] = 10.0
    first_at = last_frame_at + timedelta(seconds=1)
    result = await resume.apply(
        first_packet_at=first_at,
        first_packet_raw=first_raw,
        last_frame_at=last_frame_at,
    )
    assert result.outcome.value == "resumed"

    ingest2 = _ingest(sm2, store, hot2, repo, detector2)
    await ingest2._handle_one(first_raw, first_at)

    # ---- Phase 3: Assert truncation ----
    track = await store.read_position_track(s1.id)
    xs = sorted({s.x for s in track})
    # Frames with x in {0, 10, 20} should remain. x ≥ 30 should be gone.
    assert max(xs) == 20.0
