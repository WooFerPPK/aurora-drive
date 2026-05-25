"""T102: contract test for `/ws/coach` push half (API spec §7A)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fh6.application.services.coach_availability import CoachAvailabilityService
from fh6.application.services.coach_broker import CoachBroker
from fh6.application.services.hot_cache import HotCache
from fh6.domain.entities.coach_callout import CalloutPriority, CoachCallout
from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.domain.ports.llm_port import LLMAvailability, LLMRequest
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.infrastructure.coach.callout_engine import CalloutEngine
from fh6.infrastructure.coach.cooldown_policy import CooldownPolicy
from fh6.infrastructure.coach.detectors import OversteerDetector
from fh6.interfaces.ws.coach import make_router
from tests.contract.fake_repos import InMemoryCoachRepository


class _OKLLM:
    async def availability(self) -> LLMAvailability:
        return LLMAvailability(available=True, model="fake-coach")

    async def generate_callout(self, request: LLMRequest) -> str:
        return f"text:{request.context.get('detector_kind')}"

    def stream_answer(self, request: LLMRequest) -> AsyncIterator[str]:  # pragma: no cover
        async def _gen() -> AsyncIterator[str]:
            yield "x"

        return _gen()


def _raw_oversteer() -> FrameRaw:
    return FrameRaw(
        is_race_on=True,
        timestamp_ms=1000,
        engine={
            "rpm": 6000.0,
            "idleRpm": 900.0,
            "maxRpm": 8000.0,
            "power_w": 250_000.0,
            "torque_nm": 400.0,
            "boost_psi": 11.0,
            "fuel": 0.5,
        },
        drivetrain={"gear": 4, "clutch": 0.0, "type": "AWD"},
        motion={
            "speed_mps": 41.0,
            "velocity": {"x": 0.0, "y": 0.0, "z": 41.0},
            "acceleration": {"x": 0.0, "y": 0.0, "z": 0.0},
            "angularVelocity": {"x": 0.0, "y": 0.0, "z": 0.0},
            "orientation": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        inputs={
            "throttle": 0.8,
            "brake": 0.0,
            "clutch": 0.0,
            "handbrake": 0.0,
            "steer": 0.0,
            "drivingLine": 0.0,
            "aiBrakeDelta": 0.0,
        },
        wheels={
            "fl": {
                "slipRatio": 0.05,
                "slipAngle": 0.07,
                "combinedSlip": 0.10,
                "rotation_rad_s": 96.0,
                "suspensionTravel_norm": 0.5,
                "suspensionTravel_m": 0.07,
                "tireTemp_c": 84.4,
                "tireTemp_normWindow": 0.5,
                "onRumble": 0,
                "inPuddle": 0,
                "surfaceRumble": 0.03,
            },
            "fr": {
                "slipRatio": 0.05,
                "slipAngle": 0.07,
                "combinedSlip": 0.10,
                "rotation_rad_s": 96.0,
                "suspensionTravel_norm": 0.5,
                "suspensionTravel_m": 0.07,
                "tireTemp_c": 84.4,
                "tireTemp_normWindow": 0.5,
                "onRumble": 0,
                "inPuddle": 0,
                "surfaceRumble": 0.03,
            },
            "rl": {
                "slipRatio": 0.30,
                "slipAngle": 0.40,
                "combinedSlip": 0.45,
                "rotation_rad_s": 96.0,
                "suspensionTravel_norm": 0.5,
                "suspensionTravel_m": 0.07,
                "tireTemp_c": 84.4,
                "tireTemp_normWindow": 0.5,
                "onRumble": 0,
                "inPuddle": 0,
                "surfaceRumble": 0.03,
            },
            "rr": {
                "slipRatio": 0.30,
                "slipAngle": 0.40,
                "combinedSlip": 0.45,
                "rotation_rad_s": 96.0,
                "suspensionTravel_norm": 0.5,
                "suspensionTravel_m": 0.07,
                "tireTemp_c": 84.4,
                "tireTemp_normWindow": 0.5,
                "onRumble": 0,
                "inPuddle": 0,
                "surfaceRumble": 0.03,
            },
        },
        world={
            "carOrdinal": 1,
            "carClass": "A",
            "performanceIndex": 800,
            "numCylinders": 6,
            "carGroup": 0,
            "smashableVelDiff": 0.0,
            "smashableMass": 0.0,
        },
        race={
            "lap": 1,
            "position": 1,
            "currentLapS": 1.0,
            "lastLapS": None,
            "bestLapS": None,
            "raceTimeS": 1.0,
        },
        tail_reserved_byte=0,
    )


@pytest.fixture
def coach_broker() -> CoachBroker:
    av = CoachAvailabilityService(_OKLLM(), ttl_seconds=10.0)
    return CoachBroker(
        availability=av,
        heartbeat_interval_seconds=0.2,
        heartbeat_tick_seconds=0.05,
    )


@pytest.fixture
def app(coach_broker: CoachBroker) -> FastAPI:
    a = FastAPI()
    a.state.coach_broker = coach_broker

    def _get(ws):  # type: ignore[no-untyped-def]
        return ws.app.state.coach_broker

    a.include_router(make_router(_get))
    a.state.container = a.state

    return a


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def test_hello_includes_coach_availability(client: TestClient) -> None:
    with client.websocket_connect("/ws/coach") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert hello["coach"]["available"] is True


def test_push_callout_round_trip(
    client: TestClient, coach_broker: CoachBroker, app: FastAPI
) -> None:
    callout = CoachCallout(
        id="c_test1",
        session_id=SessionId("s_1"),
        at_session_seconds=12.0,
        priority=CalloutPriority.WARN,
        lap_context={"lap": 1, "corner": "T3"},
        text="watch the rear",
        cites=[
            {"kind": "telemetry_window", "sessionId": "s_1", "from": "x", "to": "y", "fields": []}
        ],
        model_version="fake-coach",
    )
    with client.websocket_connect("/ws/coach") as ws:
        ws.receive_json()  # hello
        client.portal.call(coach_broker.push_callout, callout)
        msg = ws.receive_json()
        assert msg["type"] == "callout"
        assert msg["id"] == "c_test1"
        assert msg["priority"] == "warn"
        assert msg["text"] == "watch the rear"
        assert msg["modelVersion"] == "fake-coach"
        assert msg["cites"]


def test_callout_engine_emits_and_respects_cooldown() -> None:
    """Integration of CalloutEngine + CooldownPolicy: sustained
    detector fires must not produce more than one callout inside the
    global rate floor (SC-004)."""
    import asyncio

    async def _run() -> None:
        clock = [0.0]
        hot = HotCache()
        repo = InMemoryCoachRepository()
        av = CoachAvailabilityService(_OKLLM(), ttl_seconds=10.0)
        sink_received: list[CoachCallout] = []

        async def sink(c: CoachCallout) -> None:
            sink_received.append(c)

        engine = CalloutEngine(
            detectors=[OversteerDetector()],
            cooldown=CooldownPolicy(),
            llm=_OKLLM(),
            coach_repo=repo,
            hot_cache=hot,
            availability=av,
            sink=sink,
            clock=lambda: clock[0],
        )
        sid = SessionId("s_eng")
        car = CarId("car_eng")
        base = datetime(2026, 5, 17, 12, 0, tzinfo=UTC)
        for i in range(30):
            f = DecodedFrame(
                session_id=sid,
                car_id=car,
                received_at=base + timedelta(milliseconds=i * 16),
                raw=_raw_oversteer(),
            )
            hot.append(f)
            await engine.on_frame(f)
        assert len(sink_received) == 1  # global rate prevented additional fires
        assert sink_received[0].priority == CalloutPriority.WARN

    asyncio.run(_run())
