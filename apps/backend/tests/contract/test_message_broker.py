"""Contract test for the `MessageBroker` port (Phase 9).

Verifies the in-process impl. The Redis impl is exercised by the
multi-worker integration test which requires a live `redis-server`.
"""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from fh6.infrastructure.messaging.inprocess_broker import InProcessBroker


async def _collect(sub, n: int, deadline_s: float = 1.0) -> list[bytes]:
    out: list[bytes] = []
    try:
        async with asyncio.timeout(deadline_s):
            async for msg in sub:
                out.append(msg)
                if len(out) >= n:
                    return out
    except TimeoutError:
        return out
    return out


@pytest.mark.asyncio
async def test_inprocess_basic_pub_sub() -> None:
    broker = InProcessBroker()
    await broker.start()
    try:
        sub = await broker.subscribe("ch")
        task = asyncio.create_task(_collect(sub, 2))
        await asyncio.sleep(0)  # let subscribe register
        await broker.publish("ch", b"hello")
        await broker.publish("ch", b"world")
        out = await task
        assert out == [b"hello", b"world"]
    finally:
        await broker.stop()


@pytest.mark.asyncio
async def test_inprocess_isolated_channels() -> None:
    broker = InProcessBroker()
    await broker.start()
    try:
        sub_a = await broker.subscribe("a")
        sub_b = await broker.subscribe("b")
        task_a = asyncio.create_task(_collect(sub_a, 1, deadline_s=0.3))
        task_b = asyncio.create_task(_collect(sub_b, 1, deadline_s=0.3))
        await asyncio.sleep(0)
        await broker.publish("a", b"to-a")
        out_a = await task_a
        out_b = await task_b
        assert out_a == [b"to-a"]
        assert out_b == []
    finally:
        await broker.stop()


@pytest.mark.asyncio
async def test_inprocess_multiple_subscribers_same_channel() -> None:
    broker = InProcessBroker()
    await broker.start()
    try:
        s1 = await broker.subscribe("ch")
        s2 = await broker.subscribe("ch")
        t1 = asyncio.create_task(_collect(s1, 1))
        t2 = asyncio.create_task(_collect(s2, 1))
        await asyncio.sleep(0)
        await broker.publish("ch", b"fan-out")
        assert await t1 == [b"fan-out"]
        assert await t2 == [b"fan-out"]
    finally:
        await broker.stop()


@pytest.mark.asyncio
async def test_inprocess_drops_oldest_on_overflow() -> None:
    broker = InProcessBroker(queue_capacity=2)
    await broker.start()
    try:
        sub = await broker.subscribe("ch")
        await broker.publish("ch", b"1")
        await broker.publish("ch", b"2")
        await broker.publish("ch", b"3")  # should drop b"1"
        out = await _collect(sub, 3, deadline_s=0.2)
        assert out == [b"2", b"3"]
    finally:
        await broker.stop()


@pytest.mark.asyncio
async def test_inprocess_subscriber_cancellation_unregisters() -> None:
    broker = InProcessBroker()
    await broker.start()
    try:
        sub = await broker.subscribe("ch")

        async def consume() -> None:
            async for _ in sub:
                pass

        task = asyncio.create_task(consume())
        await asyncio.sleep(0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        # After cancellation a publish should not raise and should not
        # backpressure on the (now-dead) subscriber's queue.
        await broker.publish("ch", b"after-cancel")
    finally:
        await broker.stop()
