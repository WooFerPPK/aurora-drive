"""Typed bundle of everything the routers/factories need.

`retention_enforcer` is the one mutable field: it can only be constructed
after `settings_repo.get_group("data")` resolves inside the lifespan, so
the lifespan assigns it once at startup. Every other field is set during
synchronous composition and stays put for the app's lifetime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from fh6.application.services.coach_availability import CoachAvailabilityService
    from fh6.application.services.coach_broker import CoachBroker
    from fh6.application.services.hot_cache import HotCache
    from fh6.application.services.live_broker import LiveBroker
    from fh6.application.services.retention_enforcer import RetentionEnforcer
    from fh6.application.services.session_manager import SessionManager
    from fh6.application.services.shift.change_point import ChangePointDetector
    from fh6.application.services.shift.shift_predictor import ShiftPredictor
    from fh6.application.use_cases.ingest_frame import IngestFrame
    from fh6.application.use_cases.rebuild_driver_fingerprint import (
        BuildSessionDriverProfile,
    )
    from fh6.application.use_cases.resume_session_on_restart import ResumeSessionOnRestart
    from fh6.domain.ports.car_repository import CarRepository
    from fh6.domain.ports.coach_repository import CoachRepository
    from fh6.domain.ports.driver_repository import DriverRepository
    from fh6.domain.ports.frame_store import FrameStore
    from fh6.domain.ports.lap_repository import LapRepository
    from fh6.domain.ports.layouts_repository import LayoutsRepository
    from fh6.domain.ports.llm_port import LLMPort
    from fh6.domain.ports.mistakes_repository import MistakesRepository
    from fh6.domain.ports.prediction_repository import PredictionRepository
    from fh6.domain.ports.replay_repository import ReplayRepository
    from fh6.domain.ports.session_events_repository import SessionEventsRepository
    from fh6.domain.ports.session_repository import SessionRepository
    from fh6.domain.ports.settings_repository import SettingsRepository
    from fh6.domain.ports.shift_predictor_repo import ShiftPredictorRepository
    from fh6.domain.ports.track_repository import TrackRepository
    from fh6.infrastructure.coach.callout_engine import CalloutEngine
    from fh6.infrastructure.config import AppConfig
    from fh6.infrastructure.ml.tire_wear.baseline_slip_energy import TireWearModel
    from fh6.infrastructure.telemetry.udp_listener import (
        TelemetryHealth,
        UDPTelemetryListener,
    )


@dataclass(slots=True)
class Container:
    config: AppConfig
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]

    settings_repo: SettingsRepository
    session_repo: SessionRepository
    car_repo: CarRepository
    lap_repo: LapRepository
    coach_repo: CoachRepository
    driver_repo: DriverRepository
    replay_repo: ReplayRepository
    layouts_repo: LayoutsRepository
    session_events_repo: SessionEventsRepository
    shift_repo: ShiftPredictorRepository
    prediction_repo: PredictionRepository
    mistakes_repo: MistakesRepository
    track_repo: TrackRepository

    frame_store: FrameStore
    live_broker: LiveBroker
    coach_broker: CoachBroker
    llm: LLMPort

    session_manager: SessionManager
    hot_cache: HotCache
    shift_predictor: ShiftPredictor
    change_point: ChangePointDetector
    coach_availability: CoachAvailabilityService
    callout_engine: CalloutEngine
    resumer: ResumeSessionOnRestart
    ingest: IngestFrame
    build_session_profile: BuildSessionDriverProfile

    tire_wear_model: TireWearModel
    listener: UDPTelemetryListener
    telemetry_health: TelemetryHealth

    retention_enforcer: RetentionEnforcer | None = None
