"""FastAPI Depends() factories for the composition graph.

Each factory reads its target out of `app.state.container` (the typed
bundle assembled by `fh6.composition.interfaces.assemble_app`) and casts
away the `Any` so call sites get a properly typed value without
per-router `# type: ignore[no-any-return]` noise.

Two consumer patterns:

  - Direct: `Depends(get_session_repo)`
  - Annotated alias (preferred): `session_repo: SessionRepoDep`

Annotated aliases let route signatures stay terse and self-documenting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, cast

from fastapi import Depends, Request

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from fh6.application.services.coach_availability import CoachAvailabilityService
    from fh6.application.services.coach_broker import CoachBroker
    from fh6.application.services.hot_cache import HotCache
    from fh6.application.services.live_broker import LiveBroker
    from fh6.application.services.retention_enforcer import RetentionEnforcer
    from fh6.application.services.session_manager import SessionManager
    from fh6.application.services.shift.shift_predictor import ShiftPredictor
    from fh6.application.use_cases.ingest_frame import IngestFrame
    from fh6.application.use_cases.rebuild_driver_fingerprint import BuildSessionDriverProfile
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
    from fh6.infrastructure.config import AppConfig
    from fh6.infrastructure.ml.tire_wear.baseline_slip_energy import TireWearModel
    from fh6.infrastructure.telemetry.udp_listener import (
        TelemetryHealth,
        UDPTelemetryListener,
    )


# ---- repositories ---------------------------------------------------------


def get_session_repo(request: Request) -> SessionRepository:
    return cast("SessionRepository", request.app.state.container.session_repo)


def get_car_repo(request: Request) -> CarRepository:
    return cast("CarRepository", request.app.state.container.car_repo)


def get_lap_repo(request: Request) -> LapRepository:
    return cast("LapRepository", request.app.state.container.lap_repo)


def get_coach_repo(request: Request) -> CoachRepository:
    return cast("CoachRepository", request.app.state.container.coach_repo)


def get_driver_repo(request: Request) -> DriverRepository:
    return cast("DriverRepository", request.app.state.container.driver_repo)


def get_replay_repo(request: Request) -> ReplayRepository:
    return cast("ReplayRepository", request.app.state.container.replay_repo)


def get_layouts_repo(request: Request) -> LayoutsRepository:
    return cast("LayoutsRepository", request.app.state.container.layouts_repo)


def get_settings_repo(request: Request) -> SettingsRepository:
    return cast("SettingsRepository", request.app.state.container.settings_repo)


def get_session_events_repo(request: Request) -> SessionEventsRepository:
    return cast("SessionEventsRepository", request.app.state.container.session_events_repo)


def get_shift_repo(request: Request) -> ShiftPredictorRepository:
    return cast("ShiftPredictorRepository", request.app.state.container.shift_repo)


def get_prediction_repo(request: Request) -> PredictionRepository:
    return cast("PredictionRepository", request.app.state.container.prediction_repo)


def get_mistakes_repo(request: Request) -> MistakesRepository:
    return cast("MistakesRepository", request.app.state.container.mistakes_repo)


def get_track_repo(request: Request) -> TrackRepository:
    return cast("TrackRepository", request.app.state.container.track_repo)


# ---- stores / brokers / clients ------------------------------------------


def get_frame_store(request: Request) -> FrameStore:
    return cast("FrameStore", request.app.state.container.frame_store)


def get_live_broker(request: Request) -> LiveBroker:
    return cast("LiveBroker", request.app.state.container.live_broker)


def get_coach_broker(request: Request) -> CoachBroker:
    return cast("CoachBroker", request.app.state.container.coach_broker)


def get_llm(request: Request) -> LLMPort:
    return cast("LLMPort", request.app.state.container.llm)


# ---- application services / use cases ------------------------------------


def get_session_manager(request: Request) -> SessionManager:
    return cast("SessionManager", request.app.state.container.session_manager)


def get_hot_cache(request: Request) -> HotCache:
    return cast("HotCache", request.app.state.container.hot_cache)


def get_shift_predictor(request: Request) -> ShiftPredictor:
    return cast("ShiftPredictor", request.app.state.container.shift_predictor)


def get_coach_availability(request: Request) -> CoachAvailabilityService:
    return cast("CoachAvailabilityService", request.app.state.container.coach_availability)


def get_retention_enforcer(request: Request) -> RetentionEnforcer:
    return cast("RetentionEnforcer", request.app.state.container.retention_enforcer)


def get_resumer(request: Request) -> ResumeSessionOnRestart:
    return cast("ResumeSessionOnRestart", request.app.state.container.resumer)


def get_ingest(request: Request) -> IngestFrame:
    return cast("IngestFrame", request.app.state.container.ingest)


def get_build_session_profile(request: Request) -> BuildSessionDriverProfile:
    return cast("BuildSessionDriverProfile", request.app.state.container.build_session_profile)


# ---- infrastructure / config ---------------------------------------------


def get_config(request: Request) -> AppConfig:
    return cast("AppConfig", request.app.state.container.config)


def get_engine(request: Request) -> AsyncEngine:
    return cast("AsyncEngine", request.app.state.container.engine)


def get_sessionmaker(request: Request) -> async_sessionmaker[AsyncSession]:
    return cast(
        "async_sessionmaker[AsyncSession]",
        request.app.state.container.sessionmaker,
    )


def get_tire_wear_model(request: Request) -> TireWearModel:
    return cast("TireWearModel", request.app.state.container.tire_wear_model)


def get_telemetry_listener(request: Request) -> UDPTelemetryListener:
    return cast("UDPTelemetryListener", request.app.state.container.listener)


def get_telemetry_health(request: Request) -> TelemetryHealth:
    return cast("TelemetryHealth", request.app.state.container.telemetry_health)


# ---- Annotated aliases (preferred at call sites) -------------------------

SessionRepoDep = Annotated["SessionRepository", Depends(get_session_repo)]
CarRepoDep = Annotated["CarRepository", Depends(get_car_repo)]
LapRepoDep = Annotated["LapRepository", Depends(get_lap_repo)]
CoachRepoDep = Annotated["CoachRepository", Depends(get_coach_repo)]
DriverRepoDep = Annotated["DriverRepository", Depends(get_driver_repo)]
ReplayRepoDep = Annotated["ReplayRepository", Depends(get_replay_repo)]
LayoutsRepoDep = Annotated["LayoutsRepository", Depends(get_layouts_repo)]
SettingsRepoDep = Annotated["SettingsRepository", Depends(get_settings_repo)]
SessionEventsRepoDep = Annotated["SessionEventsRepository", Depends(get_session_events_repo)]
ShiftRepoDep = Annotated["ShiftPredictorRepository", Depends(get_shift_repo)]
PredictionRepoDep = Annotated["PredictionRepository", Depends(get_prediction_repo)]
MistakesRepoDep = Annotated["MistakesRepository", Depends(get_mistakes_repo)]
TrackRepoDep = Annotated["TrackRepository", Depends(get_track_repo)]

FrameStoreDep = Annotated["FrameStore", Depends(get_frame_store)]
LiveBrokerDep = Annotated["LiveBroker", Depends(get_live_broker)]
CoachBrokerDep = Annotated["CoachBroker", Depends(get_coach_broker)]
LLMDep = Annotated["LLMPort", Depends(get_llm)]

SessionManagerDep = Annotated["SessionManager", Depends(get_session_manager)]
HotCacheDep = Annotated["HotCache", Depends(get_hot_cache)]
ShiftPredictorDep = Annotated["ShiftPredictor", Depends(get_shift_predictor)]
CoachAvailabilityDep = Annotated["CoachAvailabilityService", Depends(get_coach_availability)]
RetentionEnforcerDep = Annotated["RetentionEnforcer", Depends(get_retention_enforcer)]
ResumerDep = Annotated["ResumeSessionOnRestart", Depends(get_resumer)]
IngestDep = Annotated["IngestFrame", Depends(get_ingest)]
BuildSessionProfileDep = Annotated["BuildSessionDriverProfile", Depends(get_build_session_profile)]

ConfigDep = Annotated["AppConfig", Depends(get_config)]
TireWearModelDep = Annotated["TireWearModel", Depends(get_tire_wear_model)]
TelemetryListenerDep = Annotated["UDPTelemetryListener", Depends(get_telemetry_listener)]
TelemetryHealthDep = Annotated["TelemetryHealth", Depends(get_telemetry_health)]
