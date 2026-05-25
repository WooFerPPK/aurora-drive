"""Unit test for HotCache pub/sub mirror (Phase 9c).

Verifies that two HotCache instances sharing a single in-process
broker stay in lockstep — writes on one show up on the other — while
the publisher's own writes don't get double-applied via its own
subscription back-channel.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from fh6.application.services.hot_cache import HotCache
from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.infrastructure.messaging.inprocess_broker import InProcessBroker


def _frame(session: SessionId, car: CarId, ts_ms: int) -> DecodedFrame:
    raw = FrameRaw(
        is_race_on=True,
        timestamp_ms=ts_ms,
        engine={},
        drivetrain={},
        motion={
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "orientation": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
            "speed_mps": 0.0,
        },
        inputs={},
        wheels={},
        world={},
        race={},
        tail_reserved_byte=0,
    )
    return DecodedFrame(
        session_id=session,
        car_id=car,
        received_at=datetime.fromtimestamp(ts_ms / 1000.0, tz=UTC),
        raw=raw,
    )


async def _settle(times: int = 5) -> None:
    """Yield enough loop ticks for publish + subscribe round-trips."""
    for _ in range(times):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_mirrors_append_across_caches() -> None:
    broker = InProcessBroker()
    await broker.start()

    a = HotCache(broker=broker)
    b = HotCache(broker=broker)
    await a.start()
    await b.start()
    try:
        session = SessionId(uuid4())
        car = CarId(123)
        a.append(_frame(session, car, 1000))
        await _settle()
        assert b.latest_for(session, car) is not None
        assert b.latest_for(session, car).raw.timestamp_ms == 1000
    finally:
        await a.stop()
        await b.stop()
        await broker.stop()


@pytest.mark.asyncio
async def test_publisher_does_not_double_apply_own_writes() -> None:
    broker = InProcessBroker()
    await broker.start()

    a = HotCache(broker=broker)
    await a.start()
    try:
        session = SessionId(uuid4())
        car = CarId(7)
        a.append(_frame(session, car, 1000))
        a.append(_frame(session, car, 2000))
        a.append(_frame(session, car, 3000))
        await _settle(10)
        # Only the three appends should be in the window — if the
        # subscription back-channel re-applied them, length would be 6.
        assert len(a.window_for(session, car)) == 3
    finally:
        await a.stop()
        await broker.stop()


@pytest.mark.asyncio
async def test_mirrors_drop_session() -> None:
    broker = InProcessBroker()
    await broker.start()

    a = HotCache(broker=broker)
    b = HotCache(broker=broker)
    await a.start()
    await b.start()
    try:
        session = SessionId(uuid4())
        car = CarId(9)
        a.append(_frame(session, car, 1000))
        await _settle()
        assert b.latest_for(session, car) is not None
        a.drop_session(session)
        await _settle()
        assert b.latest_for(session, car) is None
    finally:
        await a.stop()
        await b.stop()
        await broker.stop()


@pytest.mark.asyncio
async def test_no_broker_means_no_mirror() -> None:
    """Sanity: HotCache(broker=None) keeps the pre-Phase-9 behaviour
    — no publish, no subscribe task, append is purely synchronous."""
    cache = HotCache()
    await cache.start()  # no-op without a broker
    try:
        session = SessionId(uuid4())
        car = CarId(1)
        cache.append(_frame(session, car, 1000))
        assert cache.latest_for(session, car) is not None
    finally:
        await cache.stop()
