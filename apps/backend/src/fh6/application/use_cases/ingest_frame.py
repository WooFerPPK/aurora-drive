"""Single consumer task that drains the UDP queue, sessionizes,
persists, updates the hot cache. Live fan-out + coach feed are wired
by the FastAPI app factory in interfaces/app.py (US1, US3 phases).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fh6.application.services import derivations, modeled_placeholder
from fh6.application.services.event_emitter import EventEmitter
from fh6.application.services.hot_cache import HotCache
from fh6.application.services.rewind_detector import RewindDetector
from fh6.application.services.session_manager import (
    BoundaryDecision,
    SessionManager,
    attach_session,
    build_car_from_raw,
)
from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.domain.entities.session import SessionCloseReason
from fh6.domain.ports.car_repository import CarRepository
from fh6.domain.ports.frame_store import FrameStore
from fh6.domain.ports.lap_repository import LapRepository
from fh6.domain.ports.session_repository import SessionRepository
from fh6.domain.value_objects.session_event import SessionEvent
from fh6.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from fh6.application.services.shift.shift_predictor import ShiftPredictor
    from fh6.application.use_cases.rebuild_driver_fingerprint import (
        BuildSessionDriverProfile,
    )
    from fh6.domain.ports.driver_repository import DriverRepository
    from fh6.domain.ports.session_events_repository import SessionEventsRepository
    from fh6.infrastructure.ml.tire_wear.baseline_slip_energy import TireWearModel

log = get_logger(__name__)


SubscribedSink = Callable[[DecodedFrame, BoundaryDecision], Awaitable[None]]


# Event kinds persisted to the historical session_events log. Lifecycle
# events (session_started / session_ended) live on the session row;
# lap_started + shift are too noisy / are reconstructable elsewhere.
PERSISTED_EVENT_KINDS: frozenset[str] = frozenset(
    {
        "lap_completed",
        "sector_completed",
        "oversteer",
        "off_track",
        "missed_upshift",
        "smashable_hit",
    }
)


def compute_style_drift(
    session_fingerprint: dict[str, float] | None,
    baseline_fingerprint: dict[str, float] | None,
) -> dict[str, float]:
    """Compute per-trait drift = session − baseline.

    Iterates over baseline keys so the result shape mirrors the 90d
    baseline (missing session traits default to 0). Returns an empty
    dict when either side is empty so downstream callers can no-op.
    """
    if not baseline_fingerprint or not session_fingerprint:
        return {}
    return {
        trait: float(session_fingerprint.get(trait, 0.0))
        - float(baseline_fingerprint.get(trait, 0.0))
        for trait in baseline_fingerprint
    }


class IngestFrame:
    # Persist the in-flight session row at most this often. Aggregates
    # are updated in memory every frame (cheap); throttling the DB write
    # keeps Postgres traffic bounded at ~1 write/s instead of ~60/s.
    SESSION_FLUSH_INTERVAL_S: float = 1.0
    # Background sweeper cadence. Independent of FLUSH_INTERVAL — its job
    # is to close sessions that have gone silent when no new frames are
    # arriving to drive on_frame's boundary check.
    IDLE_SWEEP_INTERVAL_S: float = 5.0

    def __init__(
        self,
        *,
        queue: asyncio.Queue[tuple[FrameRaw, datetime]],
        session_manager: SessionManager,
        session_repository: SessionRepository,
        frame_store: FrameStore,
        hot_cache: HotCache,
        car_repository: CarRepository | None = None,
        lap_repository: LapRepository | None = None,
        tire_wear_model: TireWearModel | None = None,
        driver_repo: DriverRepository | None = None,
        build_session_profile: BuildSessionDriverProfile | None = None,
        session_events_repo: SessionEventsRepository | None = None,
        rewind_detector: RewindDetector | None = None,
        shift_predictor: ShiftPredictor | None = None,
        event_emitter: EventEmitter | None = None,
    ) -> None:
        self._queue = queue
        self._sm = session_manager
        self._repo = session_repository
        self._store = frame_store
        self._hot = hot_cache
        self._cars = car_repository
        self._lap_repo = lap_repository
        self._tire_wear_model = tire_wear_model
        self._driver_repo = driver_repo
        self._build_session_profile = build_session_profile
        self._session_events_repo = session_events_repo
        self._rewind = rewind_detector
        self._shift = shift_predictor
        self._sinks: list[SubscribedSink] = []
        self._task: asyncio.Task[None] | None = None
        self._idle_task: asyncio.Task[None] | None = None
        self._last_session_flush_at: datetime | None = None
        # Event stream for sink: dedicated per-frame emitter so historical
        # event log (#15) is independent of the live broker's emitter.
        # Caller can inject a pre-configured one (e.g. with a shift
        # listener + recommendation provider wired). Otherwise initialized
        # lazily on first use to avoid a hard import cycle.
        self._event_emitter: EventEmitter | None = event_emitter

    def subscribe(self, sink: SubscribedSink) -> None:
        self._sinks.append(sink)

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="ingest-frame-consumer")
        self._idle_task = asyncio.create_task(
            self._idle_sweeper(), name="ingest-frame-idle-sweeper"
        )

    async def stop(self) -> None:
        for t in (self._task, self._idle_task):
            if t is None:
                continue
            t.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await t
        self._task = None
        self._idle_task = None
        # Final flush: if a session is still in flight when the app is
        # shutting down, close it with reason=shutdown so the DB row
        # reflects the true end and downstream queries don't see a
        # ghost open session forever. Use the last observed frame
        # timestamp as the end time — picking wall-clock here would mix
        # naive vs tz-aware datetimes with what the rest of the
        # pipeline emits (the UDP listener stamps frames with naive UTC).
        current = self._sm.current
        if current is not None:
            end_at = self._sm.last_frame_at or current.started_at
            final_lap = self._sm.finalize_final_lap()
            closed = self._sm.force_finalize(end_at, SessionCloseReason.SHUTDOWN)
            if closed is not None:
                await self._repo.save(closed)
                self._hot.drop_session(closed.id)
                if final_lap is not None and self._lap_repo is not None:
                    await self._lap_repo.upsert_lap(closed.id, final_lap)
                await self._maybe_persist_style_drift(closed)
                if self._rewind is not None:
                    self._rewind.on_session_closed(closed.id)

    async def _run(self) -> None:
        while True:
            raw, at = await self._queue.get()
            try:
                await self._handle_one(raw, at)
            except Exception:  # pragma: no cover — last-resort isolation
                log.exception("ingest_handler_error")

    async def _handle_one(self, raw: FrameRaw, at: datetime) -> None:
        # Rewind-stitch: if the SessionManager has a stashed closed
        # session and the incoming packet looks like a rewind (race time
        # went backward within REWIND_WINDOW_S), reopen the same session
        # instead of starting a fresh one. Must run BEFORE on_frame so
        # that adopt() sets _current before the boundary logic runs.
        if self._sm.current is None and self._lap_repo is not None:
            race_time = float(raw.race.get("raceTimeS", 0.0) or 0.0)
            wall_s = at.timestamp()
            reopened_id = self._sm.check_reopen(race_time, wall_s)
            if reopened_id is not None:
                old_session = await self._repo.get(reopened_id)
                if old_session is not None:
                    if old_session.ended_at is not None:
                        # Un-finalize: idle sweeper may have closed it
                        # while the game was rewinding.
                        old_session.ended_at = None
                        old_session.duration_s = None
                        old_session.closed_reason = None
                    # Use 'at' so on_frame's silence check sees 0-gap.
                    self._sm.adopt(old_session, at)
                    await self._repo.save(old_session)

        decision, frame = attach_session(self._sm, raw, at)

        if decision.closed_session is not None:
            await self._repo.save(decision.closed_session)
            self._hot.drop_session(decision.closed_session.id)
            # Upsert the final lap of the session that just closed.
            if decision.closed_final_lap is not None and self._lap_repo is not None:
                await self._lap_repo.upsert_lap(
                    decision.closed_session.id, decision.closed_final_lap
                )
            # Reset per-session wear state so the new session starts at 0.
            if self._tire_wear_model is not None:
                self._tire_wear_model.reset(decision.closed_session.id)
            # Compute + persist style-drift δ = session-fingerprint −
            # baseline-fingerprint. Soft-fails: drift is cosmetic and a
            # bug here must not break the close path.
            await self._maybe_persist_style_drift(decision.closed_session)
            if self._rewind is not None:
                self._rewind.on_session_closed(decision.closed_session.id)
        if decision.discarded_session_id is not None:
            # Tiny lapless menu fragment — wipe the row (cascades drop
            # any frames flushed during its brief lifetime).
            await self._repo.delete(decision.discarded_session_id)
            self._hot.drop_session(decision.discarded_session_id)
            if self._rewind is not None:
                self._rewind.on_session_closed(decision.discarded_session_id)
        if decision.opened_session is not None:
            # Upsert the car BEFORE saving the session — both sessions
            # and frames FK to cars.id, so a missing row violates the
            # constraint at insert time. Derived from this packet; later
            # frames refine `last_seen_at` via the same upsert path.
            if self._cars is not None:
                await self._cars.upsert(build_car_from_raw(raw, at))
            await self._repo.save(decision.opened_session)
            self._last_session_flush_at = at
        elif decision.current_session is not None:
            # SessionManager folds the frame's measurements into the
            # in-flight session in memory; persist the running rollups
            # on a fixed cadence so distance / top_speed / lap_count /
            # best_lap_s reflect the live drive in the DB.
            last = self._last_session_flush_at
            if last is None or (at - last).total_seconds() >= self.SESSION_FLUSH_INTERVAL_S:
                await self._repo.save(decision.current_session)
                self._last_session_flush_at = at

        # Upsert a lap completed during this frame (normal line crossing).
        if (
            decision.completed_lap is not None
            and self._lap_repo is not None
            and decision.current_session is not None
        ):
            await self._lap_repo.upsert_lap(decision.current_session.id, decision.completed_lap)

        # US1 T056 + T057: enrich tiers before fan-out + persistence so
        # every emitted frame and every stored frame carry the same
        # derived + modeled content.
        if frame.session_id is not None:
            window = self._hot.window_for(
                frame.session_id,
                frame.car_id,
                lookback=derivations.WINDOW_LOOKBACK,
            )
        else:
            window = []
        derivations.apply(frame, window)
        if self._tire_wear_model is not None:
            modeled_placeholder.apply_real_model(frame, tire_wear_model=self._tire_wear_model)
        else:
            modeled_placeholder.apply_placeholder(frame)

        # When the event-exit grace just closed a session and no new one
        # opened, the frame is session-less — the FrameStore FK to
        # sessions.id would reject it, and downstream sinks have no
        # session context to attach state to. Drop it.
        if frame.session_id is None:
            return

        # Position-based rewind detection (specs/002-rewind-detector).
        # Runs AFTER the session-less drop (the detector requires a
        # session id) and BEFORE the FrameStore append so the
        # truncation deletes the now-invalid past frames before this
        # frame is appended on top of them. Errors are isolated — a
        # detector failure must not break the ingest pipeline.
        if self._rewind is not None:
            try:
                await self._rewind.on_frame(frame)
            except Exception:
                log.exception("rewind_detector_error")

        # Adaptive shift recommendation (specs/003-shift-predictor).
        # Runs before FrameStore append so the persisted snapshot carries
        # modeled.shiftRecommendation. Errors are isolated.
        if self._shift is not None:
            try:
                session = decision.current_session or decision.opened_session
                if session is not None:
                    uptime_s = max(0.0, (at - session.started_at).total_seconds())
                    session_type_s = session.type.value
                    decoration = await self._shift.on_frame(
                        frame,
                        session_uptime_s=uptime_s,
                        session_type=session_type_s,
                    )
                    if decoration is not None:
                        frame.modeled.extras["shiftRecommendation"] = decoration.to_wire()
            except Exception:
                log.exception("shift_predictor_error")

        await self._store.append(frame)
        self._hot.append(frame)

        # Persist highlight events (#15). Done after frame.append so the
        # session_id is guaranteed present on the frame and so a failure
        # here is isolated from the time-series write path. Soft-fails.
        if self._session_events_repo is not None:
            await self._persist_session_events(frame, decision)

        # Isolate sinks: one bad sink (e.g. live_broker.on_frame raising
        # on a naive/aware TZ mismatch) must not starve the others, and
        # must not abort `_handle_one` before the next frame can be drained.
        for sink in self._sinks:
            try:
                await sink(frame, decision)
            except Exception:  # pragma: no cover — last-resort isolation
                log.exception("ingest_sink_error", sink=getattr(sink, "__qualname__", repr(sink)))

    async def _persist_session_events(
        self,
        frame: DecodedFrame,
        decision: BoundaryDecision,
    ) -> None:
        """Run the per-frame `EventEmitter`, filter to `PERSISTED_EVENT_KINDS`
        and append to the historical event log keyed by session.

        `at_s` is wall-clock seconds since the owning session's
        `started_at` so the highlight reel plays back independently of
        absolute timestamps. Soft-fails to keep the ingest loop alive.
        """
        try:
            # Lazy emitter init avoids forcing every IngestFrame consumer
            # to construct one upfront.
            if self._event_emitter is None:
                self._event_emitter = EventEmitter()
            emitter = self._event_emitter
            boundary_events = emitter.on_boundary(decision, frame.received_at)
            frame_events = emitter.on_frame(frame)
            raw_events = boundary_events + frame_events
            if not raw_events:
                return
            session = decision.current_session or decision.opened_session
            if session is None:
                return
            session_id = str(session.id)
            started_at = session.started_at

            to_save: list[SessionEvent] = []
            for ev in raw_events:
                if ev.kind not in PERSISTED_EVENT_KINDS:
                    continue
                at_s = max(0.0, (ev.at - started_at).total_seconds())
                to_save.append(
                    SessionEvent(
                        session_id=session_id,
                        at_s=at_s,
                        kind=ev.kind,
                        payload=dict(ev.payload),
                    )
                )
            if to_save and self._session_events_repo is not None:
                await self._session_events_repo.save_many(to_save)
        except Exception as err:
            log.warning("session_events_persist_failed", error=str(err))

    async def _maybe_persist_style_drift(self, closed_session) -> None:  # type: ignore[no-untyped-def]
        """Compute fingerprint δ for `closed_session` vs the global 90d
        baseline and persist it on the session row.

        Wired as a no-op when either dependency is missing so existing
        unit-test constructors (which don't pass driver_repo /
        build_session_profile) keep working.
        """
        if self._driver_repo is None or self._build_session_profile is None:
            return
        try:
            session_result = await self._build_session_profile(closed_session)
            baseline_profile = await self._driver_repo.get()
            baseline = (
                getattr(baseline_profile, "fingerprint_baseline_90d", None)
                if baseline_profile is not None
                else None
            )
            session_fp = (
                getattr(session_result, "fingerprint", None) if session_result is not None else None
            )
            drift = compute_style_drift(session_fp, baseline)
            if drift:
                closed_session.style_drift_delta = drift
                await self._repo.save(closed_session)
        except Exception as err:
            log.warning("style_drift_compute_failed", error=str(err))

    async def _idle_sweeper(self) -> None:
        """Periodically finalize the in-flight session if the stream
        has gone silent. on_frame's silence-split only fires when a
        new packet arrives — without this sweeper, a session whose
        stream stops cold stays in_flight forever in the DB.

        Wall-clock `now` is matched to the naive/aware regime of the
        session's last_frame_at to avoid the
        `can't compare offset-naive and offset-aware datetimes` error
        (UDP listener stamps naive UTC; some entry points pass aware).
        """
        while True:
            try:
                await asyncio.sleep(self.IDLE_SWEEP_INTERVAL_S)
                last = self._sm.last_frame_at
                if last is None:
                    continue
                now = (
                    datetime.now(UTC)
                    if last.tzinfo is not None
                    else datetime.now(UTC).replace(tzinfo=None)
                )
                # Capture final lap before finalizing so lap state is
                # still intact when finalize_final_lap runs.
                final_lap = None
                if self._sm.current is not None:
                    final_lap = self._sm.finalize_final_lap()
                closed = self._sm.maybe_finalize_idle(now)
                if closed is not None:
                    await self._repo.save(closed)
                    self._hot.drop_session(closed.id)
                    if final_lap is not None and self._lap_repo is not None:
                        await self._lap_repo.upsert_lap(closed.id, final_lap)
                    await self._maybe_persist_style_drift(closed)
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover — last-resort isolation
                log.exception("idle_sweeper_error")
