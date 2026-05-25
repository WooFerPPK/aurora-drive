"""Build application services + use cases from infrastructure adapters.

Includes the shift-predictor stack, ingest pipeline, coach callouts, and
the WS brokers (kept here because they're consumed by application-tier
wiring — `live_broker` for the change-point event fan-out, `coach_broker`
as the callout sink).
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from fh6.application.services.coach_availability import CoachAvailabilityService
from fh6.application.services.coach_broker import CoachBroker
from fh6.application.services.event_emitter import Event, EventEmitter
from fh6.application.services.hot_cache import HotCache
from fh6.application.services.live_broker import LiveBroker
from fh6.application.services.rewind_detector import RewindDetector
from fh6.application.services.session_manager import SessionManager
from fh6.application.services.shift.bin_trainer import BinTrainer
from fh6.application.services.shift.change_point import ChangePointDetector, ChangePointEvent
from fh6.application.services.shift.class_prior import ClassPriorBuilder
from fh6.application.services.shift.curve_resolver import ShiftCurveResolver
from fh6.application.services.shift.ratio_kalman import RatioKalman
from fh6.application.services.shift.shift_event_evaluator import ShiftEventEvaluator
from fh6.application.services.shift.shift_predictor import ShiftPredictor
from fh6.application.services.shift.transmission_mode import TransmissionModeInferer
from fh6.application.use_cases.ingest_frame import IngestFrame
from fh6.application.use_cases.rebuild_driver_fingerprint import (
    BuildSessionDriverProfile,
)
from fh6.application.use_cases.resume_session_on_restart import ResumeSessionOnRestart
from fh6.infrastructure.coach.callout_engine import CalloutEngine
from fh6.infrastructure.coach.cooldown_policy import CooldownPolicy
from fh6.infrastructure.coach.detectors import (
    LateThrottleDetector,
    MissedUpshiftDetector,
    OffTrackDetector,
    OversteerDetector,
)
from fh6.infrastructure.logging import get_logger

if TYPE_CHECKING:
    from fh6.composition.infrastructure import Infrastructure


log = get_logger(__name__)


@dataclass(slots=True)
class Application:
    session_manager: SessionManager
    hot_cache: HotCache
    shift_predictor: ShiftPredictor
    change_point: ChangePointDetector
    coach_availability: CoachAvailabilityService
    callout_engine: CalloutEngine
    live_broker: LiveBroker
    coach_broker: CoachBroker
    resumer: ResumeSessionOnRestart
    ingest: IngestFrame
    build_session_profile: BuildSessionDriverProfile


def build_application(infra: Infrastructure) -> Application:
    config = infra.config

    session_manager = SessionManager(silence_seconds=60.0)
    # Phase 9: HotCache mirrors writes via the shared message broker so
    # every uvicorn worker sees them; reads stay rAF-hot per-worker.
    hot_cache = HotCache(broker=infra.message_broker)

    rewind_detector = RewindDetector(
        frame_store=infra.frame_store,
        continuity_threshold_m=config.rewind_continuity_threshold_m,
        match_tolerance_m=config.rewind_match_tolerance_m,
        yaw_tolerance_rad=config.rewind_yaw_tolerance_rad,
        pause_floor=timedelta(milliseconds=config.rewind_pause_floor_ms),
        hot_cache=hot_cache,
    )
    session_manager.add_adopt_listener(rewind_detector.on_adopt)

    # WS brokers are constructed before the shift stack so the change-point
    # callback can capture `live_broker` directly instead of late-binding
    # through `app.state`. Both brokers ride the shared `message_broker`
    # port so a single ingest worker can fan out to WS subscribers across
    # multiple uvicorn workers (Phase 9).
    live_broker = LiveBroker(broker=infra.message_broker)
    coach_availability = CoachAvailabilityService(infra.llm)
    coach_broker = CoachBroker(
        availability=coach_availability,
        broker=infra.message_broker,
    )

    # Shift predictor stack (specs/003-shift-predictor).
    shift_curve_resolver = ShiftCurveResolver(config=config)
    shift_bin_trainer = BinTrainer(half_life_samples=config.shift_ewma_half_life_samples)
    shift_ratio_kalman = RatioKalman()
    shift_class_prior = ClassPriorBuilder(repo=infra.shift_repo)
    shift_event_evaluator = ShiftEventEvaluator(
        config=config,
        repo=infra.shift_repo,
        curve_resolver=shift_curve_resolver,
    )

    bg_tasks: set[asyncio.Task[None]] = set()

    def _on_change_point(event: ChangePointEvent) -> None:
        log.info(
            "shift_change_point",
            car_ordinal=event.fingerprint.car_ordinal,
            direction=event.direction,
            bins_affected=event.bins_affected,
        )
        # Fan out to live subscribers (FR-013 + FR-034). Scheduled on the
        # event loop because the change-point detector callback is sync.
        ev = Event(
            kind="engine_curve_change",
            at=event.at,
            payload={
                "carOrdinal": event.fingerprint.car_ordinal,
                "performanceIndex": event.fingerprint.performance_index,
                "numCylinders": event.fingerprint.num_cylinders,
                "direction": event.direction,
                "binsAffected": event.bins_affected,
            },
        )
        # No running loop at boot — silently skip; we'd just log otherwise.
        with suppress(RuntimeError):
            task = asyncio.create_task(live_broker.push_event(ev))
            bg_tasks.add(task)
            task.add_done_callback(bg_tasks.discard)

    shift_change_point = ChangePointDetector(
        config=config,
        on_change_point=_on_change_point,
    )
    shift_transmission_mode_inferer = TransmissionModeInferer(config=config)
    shift_predictor = ShiftPredictor(
        config=config,
        repo=infra.shift_repo,
        bin_trainer=shift_bin_trainer,
        ratio_kalman=shift_ratio_kalman,
        curve_resolver=shift_curve_resolver,
        class_prior=shift_class_prior,
        change_point=shift_change_point,
        shift_listener=shift_event_evaluator,
        transmission_mode_inferer=shift_transmission_mode_inferer,
    )

    # Eviction of per-session shift state on session-started (FR-003).
    session_manager.add_session_started_listener(shift_predictor.on_session_started)

    # Pre-configure the historical EventEmitter with the shift recommendation
    # provider so persisted shift events include recommendedRpm/confidence
    # (FR-016).
    event_emitter = EventEmitter()
    event_emitter.set_recommendation_provider(shift_predictor.recommendation_provider())

    build_session_profile = BuildSessionDriverProfile(sessions=infra.session_repo)
    ingest = IngestFrame(
        queue=infra.telemetry_queue,
        session_manager=session_manager,
        session_repository=infra.session_repo,
        frame_store=infra.frame_store,
        hot_cache=hot_cache,
        car_repository=infra.car_repo,
        lap_repository=infra.lap_repo,
        tire_wear_model=infra.tire_wear_model,
        driver_repo=infra.driver_repo,
        build_session_profile=build_session_profile,
        session_events_repo=infra.session_events_repo,
        rewind_detector=rewind_detector,
        shift_predictor=shift_predictor,
        event_emitter=event_emitter,
    )
    resumer = ResumeSessionOnRestart(infra.session_repo, session_manager)

    ingest.subscribe(live_broker.on_frame)

    # Coach pipeline (US3).
    callout_engine = CalloutEngine(
        detectors=[
            OversteerDetector(),
            MissedUpshiftDetector(),
            OffTrackDetector(),
            LateThrottleDetector(),
        ],
        cooldown=CooldownPolicy(),
        llm=infra.llm,
        coach_repo=infra.coach_repo,
        hot_cache=hot_cache,
        availability=coach_availability,
        sink=coach_broker.push_callout,
    )

    async def _coach_sink(frame, _decision) -> None:  # type: ignore[no-untyped-def]
        await callout_engine.on_frame(frame)

    ingest.subscribe(_coach_sink)

    return Application(
        session_manager=session_manager,
        hot_cache=hot_cache,
        shift_predictor=shift_predictor,
        change_point=shift_change_point,
        coach_availability=coach_availability,
        callout_engine=callout_engine,
        live_broker=live_broker,
        coach_broker=coach_broker,
        resumer=resumer,
        ingest=ingest,
        build_session_profile=build_session_profile,
    )
