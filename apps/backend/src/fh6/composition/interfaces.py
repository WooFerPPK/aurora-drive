"""Mount middleware, lifespan, and routers; return the FastAPI app.

The lifespan owns runtime concerns that can't be done synchronously at
boot: loading the data-retention policy from settings, starting the UDP
listener, ingest, broker, retention enforcer, and the stale-session
sweeper. RetentionEnforcer is the one piece of state created here (not in
`application.py`) because its policy is sourced from an async settings
read.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fh6.application.services.retention_enforcer import RetentionEnforcer, RetentionPolicy
from fh6.composition.container import Container
from fh6.infrastructure.logging import get_logger
from fh6.interfaces.rest.cars_router import data_router as cars_data_router
from fh6.interfaces.rest.cars_router import router as cars_router
from fh6.interfaces.rest.coach_router import router as coach_rest_router
from fh6.interfaces.rest.driver_router import router as driver_router
from fh6.interfaces.rest.health_router import router as health_router
from fh6.interfaces.rest.layouts_router import router as layouts_router
from fh6.interfaces.rest.predict_router import router as predict_router
from fh6.interfaces.rest.replay_router import router as replay_router
from fh6.interfaces.rest.sessions_router import router as sessions_router
from fh6.interfaces.rest.settings_router import router as settings_router
from fh6.interfaces.rest.shift_router import router as shift_router
from fh6.interfaces.rest.track_router import router as track_router
from fh6.interfaces.ws.coach import make_router as make_coach_router
from fh6.interfaces.ws.live import make_router as make_live_router

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

    from fh6.application.services.coach_broker import CoachBroker
    from fh6.application.services.live_broker import LiveBroker
    from fh6.composition.application import Application
    from fh6.composition.infrastructure import Infrastructure

log = get_logger(__name__)


def assemble_app(infra: Infrastructure, application: Application) -> FastAPI:
    container = Container(
        config=infra.config,
        engine=infra.engine,
        sessionmaker=infra.sessionmaker,
        settings_repo=infra.settings_repo,
        session_repo=infra.session_repo,
        car_repo=infra.car_repo,
        lap_repo=infra.lap_repo,
        coach_repo=infra.coach_repo,
        driver_repo=infra.driver_repo,
        replay_repo=infra.replay_repo,
        layouts_repo=infra.layouts_repo,
        session_events_repo=infra.session_events_repo,
        shift_repo=infra.shift_repo,
        prediction_repo=infra.prediction_repo,
        mistakes_repo=infra.mistakes_repo,
        track_repo=infra.track_repo,
        frame_store=infra.frame_store,
        live_broker=application.live_broker,
        coach_broker=application.coach_broker,
        llm=infra.llm,
        session_manager=application.session_manager,
        hot_cache=application.hot_cache,
        shift_predictor=application.shift_predictor,
        change_point=application.change_point,
        coach_availability=application.coach_availability,
        callout_engine=application.callout_engine,
        resumer=application.resumer,
        ingest=application.ingest,
        build_session_profile=application.build_session_profile,
        tire_wear_model=infra.tire_wear_model,
        listener=infra.listener,
        telemetry_health=infra.listener.health,
    )

    silence_seconds = application.session_manager.silence_threshold.total_seconds()
    sweeper_interval_s = max(silence_seconds, 30.0)

    async def _stale_session_sweeper() -> None:
        # ResumeSessionOnRestart only finalizes the latest open session at
        # boot; older corpses from prior restarts (or pre-cascade-migration
        # crashes) accumulate and silently block bulk delete. Periodic
        # sweep closes any open session older than the silence threshold
        # that isn't the one SessionManager currently owns.
        while True:
            try:
                await asyncio.sleep(sweeper_interval_s)
                cutoff = datetime.now(UTC) - timedelta(seconds=silence_seconds)
                current = application.session_manager.current
                except_id = current.id if current is not None else None
                count = await infra.session_repo.finalize_stale(
                    older_than=cutoff,
                    except_id=except_id,
                )
                if count:
                    log.info("stale_sessions_finalized", count=count)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("stale_session_sweeper_error")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await infra.settings_repo.seed_defaults_if_empty()

        # Retention policy is sourced from the `data` settings group
        # (FR-039a, Clarification Q2). Dynamic refresh on settings PATCH
        # is a follow-up — restart picks up new values.
        data_settings = await infra.settings_repo.get_group("data")
        retention_enforcer = RetentionEnforcer(
            session_repo=infra.session_repo,
            car_repo=infra.car_repo,
            frame_store=infra.frame_store,
            policy=RetentionPolicy(
                retention_days=int(data_settings.get("retentionDays", 90)),
                max_bytes_per_car=int(data_settings.get("maxBytesPerCar", 5_368_709_120)),
            ),
        )
        container.retention_enforcer = retention_enforcer

        # MessageBroker must come up before any publisher fires; LiveBroker
        # owns the broker only in tests, so explicitly start it here.
        await infra.message_broker.start()
        await application.hot_cache.start()
        await infra.listener.start()
        application.ingest.start()
        await application.live_broker.start()
        await application.coach_broker.start()
        retention_enforcer.start()
        sweeper_task = asyncio.create_task(_stale_session_sweeper())
        log.info(
            "app_started",
            listen_port=infra.config.listen_port,
            http_port=infra.config.http_port,
        )
        try:
            yield
        finally:
            sweeper_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await sweeper_task
            await retention_enforcer.stop()
            await application.coach_broker.stop()
            await application.live_broker.stop()
            await application.ingest.stop()
            await infra.listener.stop()
            await application.hot_cache.stop()
            await infra.message_broker.stop()
            await infra.engine.dispose()

    app = FastAPI(
        title="Forza Racer Telemetry Backend",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^(http://localhost(:\d+)?|app://.*)$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.container = container

    _mount_routers(app)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _mount_routers(app: FastAPI) -> None:
    app.include_router(cars_router, prefix="/api/cars", tags=["cars"])
    app.include_router(sessions_router, prefix="/api/sessions", tags=["sessions"])
    app.include_router(track_router, prefix="/api/track", tags=["track"])
    app.include_router(coach_rest_router, prefix="/api/coach", tags=["coach"])
    app.include_router(predict_router, prefix="/api/predict", tags=["predict"])
    app.include_router(shift_router, prefix="/api/predict/shift", tags=["predict"])
    app.include_router(replay_router, prefix="/api/replay", tags=["replay"])
    app.include_router(driver_router, prefix="/api/driver", tags=["driver"])
    app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
    app.include_router(layouts_router, prefix="/api/layouts", tags=["layouts"])
    app.include_router(cars_data_router, prefix="/api/data", tags=["data"])
    app.include_router(health_router, prefix="/health", tags=["health"])

    def _get_live_broker(ws: WebSocket) -> LiveBroker:
        return cast("LiveBroker", ws.app.state.container.live_broker)

    def _get_coach_broker(ws: WebSocket) -> CoachBroker:
        return cast("CoachBroker", ws.app.state.container.coach_broker)

    app.include_router(make_live_router(_get_live_broker))
    app.include_router(make_coach_router(_get_coach_broker))
