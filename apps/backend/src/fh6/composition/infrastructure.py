"""Build infrastructure adapters from `AppConfig`.

These are the things that talk to the outside world (Postgres, UDP socket,
Claude headless) plus the synchronous primitives ingest needs (decoder,
queue). They depend only on config — no services from the application
tier reach in here.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fh6.infrastructure.db.base import make_engine, make_sessionmaker
from fh6.infrastructure.db.repositories.cars import PgCarRepository
from fh6.infrastructure.db.repositories.coach import PgCoachRepository
from fh6.infrastructure.db.repositories.driver import PgDriverRepository
from fh6.infrastructure.db.repositories.laps import PgLapRepository
from fh6.infrastructure.db.repositories.layouts import PgLayoutsRepository
from fh6.infrastructure.db.repositories.mistakes import PgMistakesRepository
from fh6.infrastructure.db.repositories.predictions import PgPredictionRepository
from fh6.infrastructure.db.repositories.replays import PgReplayRepository
from fh6.infrastructure.db.repositories.session_events import PgSessionEventsRepository
from fh6.infrastructure.db.repositories.sessions import PgSessionRepository
from fh6.infrastructure.db.repositories.settings import PgSettingsRepository
from fh6.infrastructure.db.repositories.shift_predictor import SqlShiftPredictorRepository
from fh6.infrastructure.db.repositories.tracks import PgTrackRepository
from fh6.infrastructure.llm.claude_headless_adapter import ClaudeHeadlessLLMAdapter
from fh6.infrastructure.llm.dry_run_adapter import DryRunLLMAdapter
from fh6.infrastructure.messaging.inprocess_broker import InProcessBroker
from fh6.infrastructure.messaging.redis_broker import RedisBroker
from fh6.infrastructure.ml.tire_wear.baseline_slip_energy import TireWearModel
from fh6.infrastructure.telemetry.fh6_decoder import FH6PacketDecoder
from fh6.infrastructure.telemetry.udp_listener import UDPTelemetryListener
from fh6.infrastructure.timeseries.frame_store import TimescaleFrameStore

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from fh6.domain.entities.frame import FrameRaw
    from fh6.domain.ports.llm_port import LLMPort
    from fh6.domain.ports.messaging import MessageBroker
    from fh6.infrastructure.config import AppConfig


@dataclass(slots=True)
class Infrastructure:
    config: AppConfig
    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]

    settings_repo: PgSettingsRepository
    session_repo: PgSessionRepository
    car_repo: PgCarRepository
    lap_repo: PgLapRepository
    coach_repo: PgCoachRepository
    driver_repo: PgDriverRepository
    replay_repo: PgReplayRepository
    layouts_repo: PgLayoutsRepository
    session_events_repo: PgSessionEventsRepository
    shift_repo: SqlShiftPredictorRepository
    prediction_repo: PgPredictionRepository
    mistakes_repo: PgMistakesRepository
    track_repo: PgTrackRepository

    frame_store: TimescaleFrameStore
    llm: LLMPort
    message_broker: MessageBroker

    tire_wear_model: TireWearModel
    decoder: FH6PacketDecoder
    telemetry_queue: asyncio.Queue[tuple[FrameRaw, datetime]]
    listener: UDPTelemetryListener


def build_infrastructure(config: AppConfig) -> Infrastructure:
    engine = make_engine(config.db_dsn)
    sessionmaker = make_sessionmaker(engine)

    frame_store = TimescaleFrameStore(sessionmaker)
    llm: LLMPort = DryRunLLMAdapter() if config.llm_dry_run else ClaudeHeadlessLLMAdapter()

    # Phase 9: cross-worker pub/sub. Redis when configured (required for
    # `uvicorn --workers >1`), in-process queues otherwise — single-worker
    # dev/test keeps working without a live Redis.
    message_broker: MessageBroker = (
        RedisBroker(config.redis_url) if config.redis_url else InProcessBroker()
    )

    decoder = FH6PacketDecoder()
    telemetry_queue: asyncio.Queue[tuple[FrameRaw, datetime]] = asyncio.Queue()
    listener = UDPTelemetryListener(
        host=config.listen_addr,
        port=config.listen_port,
        decoder=decoder,
        queue=telemetry_queue,
    )

    return Infrastructure(
        config=config,
        engine=engine,
        sessionmaker=sessionmaker,
        settings_repo=PgSettingsRepository(sessionmaker),
        session_repo=PgSessionRepository(sessionmaker),
        car_repo=PgCarRepository(sessionmaker),
        lap_repo=PgLapRepository(sessionmaker),
        coach_repo=PgCoachRepository(sessionmaker),
        driver_repo=PgDriverRepository(sessionmaker),
        replay_repo=PgReplayRepository(sessionmaker),
        layouts_repo=PgLayoutsRepository(sessionmaker),
        session_events_repo=PgSessionEventsRepository(sessionmaker),
        shift_repo=SqlShiftPredictorRepository(sessionmaker),
        prediction_repo=PgPredictionRepository(sessionmaker),
        mistakes_repo=PgMistakesRepository(sessionmaker),
        track_repo=PgTrackRepository(sessionmaker),
        frame_store=frame_store,
        llm=llm,
        message_broker=message_broker,
        tire_wear_model=TireWearModel(),
        decoder=decoder,
        telemetry_queue=telemetry_queue,
        listener=listener,
    )
