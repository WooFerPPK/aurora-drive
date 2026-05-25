"""Phase 9f: cross-worker pub/sub via Redis.

Two `RedisBroker` instances share a single Redis. Subscribers on one
instance see messages published from the other — the contract that
makes `uvicorn --workers >1` viable for the live stream.

Also exercises the LiveBroker layer end-to-end: a publishing LiveBroker
on instance A publishes a frame; WS adapters wired to LiveBrokers on
instances B and C both receive the frame envelope.

Skips when `redis-server` is not reachable on `127.0.0.1:6379`. The
process-local in-process broker keeps unit/contract tests green without
Redis; this file's contract requires the real thing.
"""

from __future__ import annotations

import asyncio
import json
import socket

import pytest

from fh6.application.services.live_broker import LiveBroker
from fh6.application.services.session_manager import (
    BoundaryDecision,
    SessionManager,
    attach_session,
)
from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.infrastructure.messaging.redis_broker import RedisBroker

REDIS_URL = "redis://127.0.0.1:6379/15"  # db 15 to avoid stepping on other state


def _redis_reachable() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 6379), timeout=0.5):
            return True
    except OSError:
        return False


requires_redis = pytest.mark.skipif(
    not _redis_reachable(),
    reason="redis-server not reachable on 127.0.0.1:6379 — run `apt install redis-server`",
)


def _raw() -> FrameRaw:
    # Populated enough to satisfy EventEmitter (race.lap / position /
    # bestLapS) and HotCache (motion.position for window math); broker
    # fan-out doesn't introspect the content.
    return FrameRaw(
        is_race_on=True,
        timestamp_ms=1000,
        engine={"rpm": 3000.0, "idleRpm": 800.0, "maxRpm": 7000.0},
        drivetrain={"gear": 3},
        motion={
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "orientation": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
            "velocity": {"x": 0.0, "y": 0.0, "z": 0.0},
            "acceleration": {"x": 0.0, "y": 0.0, "z": 0.0},
            "angularVelocity": {"x": 0.0, "y": 0.0, "z": 0.0},
            "speed_mps": 0.0,
        },
        inputs={"throttle": 0.0, "brake": 0.0, "steer": 0.0},
        wheels={
            corner: {
                "slipRatio": 0.0,
                "slipAngle": 0.0,
                "combinedSlip": 0.0,
                "rotation_rad_s": 0.0,
                "suspensionTravel_norm": 0.5,
                "suspensionTravel_m": 0.05,
                "tireTemp_c": 80.0,
                "tireTemp_normWindow": 0.5,
                "onRumble": 0,
                "inPuddle": 0,
                "surfaceRumble": 0.0,
            }
            for corner in ("fl", "fr", "rl", "rr")
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


def _frame_and_decision() -> tuple[DecodedFrame, BoundaryDecision]:
    """Build a sessionized frame for broker fan-out tests.

    Skips `derivations.apply` / `modeled_placeholder` because the
    minimal `_raw()` fixture omits the wheel sub-dicts those expect —
    the broker layer doesn't care about derived/modeled tiers, it just
    serializes whatever frame it's given.
    """
    from datetime import UTC, datetime

    sm = SessionManager(silence_seconds=60.0)
    at = datetime(2026, 5, 25, 12, 0, 0, tzinfo=UTC)
    decision, frame = attach_session(sm, _raw(), at)
    return frame, decision


@requires_redis
@pytest.mark.asyncio
async def test_redis_broker_cross_instance_publish() -> None:
    """Two RedisBroker instances + one Redis. Publish on A → receive on B."""
    a = RedisBroker(REDIS_URL)
    b = RedisBroker(REDIS_URL)
    await a.start()
    await b.start()
    try:
        sub = await b.subscribe("phase9:test")
        # tiny grace for SUBSCRIBE to register on the Redis side
        await asyncio.sleep(0.05)
        await a.publish("phase9:test", b"hello")
        msg = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
        assert msg == b"hello"
    finally:
        await a.stop()
        await b.stop()


@requires_redis
@pytest.mark.asyncio
async def test_multi_worker_live_broker_fan_out() -> None:
    """Publishing LiveBroker on instance A → LiveBroker subscribers on
    instances B and C both receive the frame envelope.

    Models the production topology: one ingest worker publishing,
    multiple WS workers consuming. Tests just below the WS adapter
    layer so a Redis hop in this process == a Redis hop across uvicorn
    workers (same network round-trip semantics)."""
    redis_a = RedisBroker(REDIS_URL)
    redis_b = RedisBroker(REDIS_URL)
    redis_c = RedisBroker(REDIS_URL)
    await redis_a.start()
    await redis_b.start()
    await redis_c.start()

    publisher = LiveBroker(broker=redis_a)
    consumer_b = LiveBroker(broker=redis_b)
    consumer_c = LiveBroker(broker=redis_c)
    await publisher.start()
    await consumer_b.start()
    await consumer_c.start()

    try:
        sub_b = await consumer_b.subscribe_frames()
        sub_c = await consumer_c.subscribe_frames()
        await asyncio.sleep(0.05)

        frame, decision = _frame_and_decision()
        await publisher.on_frame(frame, decision)

        raw_b = await asyncio.wait_for(sub_b.__anext__(), timeout=2.0)
        raw_c = await asyncio.wait_for(sub_c.__anext__(), timeout=2.0)

        env_b = json.loads(raw_b)
        env_c = json.loads(raw_c)
        assert env_b["frame"]["type"] == "frame"
        assert env_c["frame"]["type"] == "frame"
        # Same envelope on both consumers — there's one source of truth.
        assert env_b == env_c
    finally:
        await publisher.stop()
        await consumer_b.stop()
        await consumer_c.stop()
        await redis_a.stop()
        await redis_b.stop()
        await redis_c.stop()


@requires_redis
@pytest.mark.asyncio
async def test_redis_publishes_isolated_by_channel() -> None:
    """Sanity: pub on channel X must not show up on channel Y."""
    a = RedisBroker(REDIS_URL)
    b = RedisBroker(REDIS_URL)
    await a.start()
    await b.start()
    try:
        sub_y = await b.subscribe("phase9:y")
        await asyncio.sleep(0.05)
        await a.publish("phase9:x", b"to-x")
        # Should time out — no message on y.
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(sub_y.__anext__(), timeout=0.3)
        # ... but a publish on y should arrive.
        await a.publish("phase9:y", b"to-y")
        msg = await asyncio.wait_for(sub_y.__anext__(), timeout=2.0)
        assert msg == b"to-y"
    finally:
        await a.stop()
        await b.stop()


@requires_redis
@pytest.mark.asyncio
async def test_publisher_cleanup_does_not_leak_into_next_run() -> None:
    """Each LiveBroker stop() must release its Redis resources cleanly
    — otherwise a flapping ingest worker would leak connections."""
    for _ in range(3):
        redis = RedisBroker(REDIS_URL)
        await redis.start()
        broker = LiveBroker(broker=redis)
        await broker.start()
        sub = await broker.subscribe_frames()
        # quick round-trip then teardown
        await asyncio.sleep(0.02)
        # cancel the iterator so its background task can detach
        await sub.aclose()  # type: ignore[attr-defined]
        await broker.stop()
        await redis.stop()


@requires_redis
@pytest.mark.asyncio
async def test_hot_cache_mirror_across_workers() -> None:
    """Phase 9c contract: HotCache writes on worker A show up in worker
    B's local cache, without B having to do a Redis read on every
    request — the rAF-hot path stays in-process."""
    from datetime import UTC, datetime
    from uuid import uuid4

    from fh6.application.services.hot_cache import HotCache
    from fh6.domain.value_objects.ids import CarId, SessionId

    redis_a = RedisBroker(REDIS_URL)
    redis_b = RedisBroker(REDIS_URL)
    await redis_a.start()
    await redis_b.start()

    a = HotCache(broker=redis_a)
    b = HotCache(broker=redis_b)
    await a.start()
    await b.start()
    try:
        session = SessionId(uuid4())
        car = CarId(42)
        raw = _raw()
        frame = DecodedFrame(
            session_id=session,
            car_id=car,
            received_at=datetime.now(UTC),
            raw=raw,
        )
        a.append(frame)

        # Allow the publish round-trip + subscriber apply.
        deadline = asyncio.get_event_loop().time() + 2.0
        while asyncio.get_event_loop().time() < deadline:
            if b.latest_for(session, car) is not None:
                break
            await asyncio.sleep(0.05)

        latest = b.latest_for(session, car)
        assert latest is not None
        assert latest.car_id == car
    finally:
        await a.stop()
        await b.stop()
        await redis_a.stop()
        await redis_b.stop()
