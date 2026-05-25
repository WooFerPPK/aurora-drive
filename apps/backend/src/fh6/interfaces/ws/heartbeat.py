"""Heartbeat scheduler (T052).

Each subscriber tracks the timestamp of its last outbound message. A
single coroutine per subscriber ticks every 1 s, computing whether 5 s
have elapsed since the last emission, and if so enqueues a heartbeat.

The heartbeat is enqueued via the same drop-oldest path as frames so a
stalled reader degrades gracefully (research R-13).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

HEARTBEAT_INTERVAL = timedelta(seconds=5)
TICK_INTERVAL_SECONDS = 1.0


async def run_heartbeat(
    *,
    last_emit_at: Callable[[], datetime],
    emit: Callable[[datetime], Awaitable[None]],
    stop: asyncio.Event,
    tick_seconds: float = TICK_INTERVAL_SECONDS,
    heartbeat_interval_seconds: float | None = None,
) -> None:
    """Run forever until `stop` is set. Emits via `emit(now)` when idle."""
    interval = (
        timedelta(seconds=heartbeat_interval_seconds)
        if heartbeat_interval_seconds is not None
        else HEARTBEAT_INTERVAL
    )
    try:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=tick_seconds)
                return
            except TimeoutError:
                pass
            now = datetime.now(UTC)
            if now - last_emit_at() >= interval:
                await emit(now)
    except asyncio.CancelledError:
        return
