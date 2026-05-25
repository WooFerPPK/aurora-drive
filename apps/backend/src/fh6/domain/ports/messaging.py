"""Pub/sub primitive for cross-worker message fan-out (Phase 9).

Implementations:
  * `InProcessBroker` — asyncio queues, no external dependency. Default
    when `FH6_REDIS_URL` is unset, so single-worker dev/test keeps
    working without Redis.
  * `RedisBroker` — Redis pub/sub. Required for `uvicorn --workers >1`
    so subscribers on one worker see frames published from another.

Channels are flat string names. Payloads are JSON-encoded bytes; the
broker does not interpret them. Subscribers receive a stream of bytes
chunks via an async iterator.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol


class MessageBroker(Protocol):
    """Cross-process publish/subscribe primitive.

    Lifecycle: `start()` once at app boot, `stop()` at shutdown.
    `publish()` and `subscribe()` may be called concurrently after start.

    `subscribe()` is async because impls may need to register with a
    remote service (Redis SUBSCRIBE) before the first message can be
    received — without that, publishes that race the subscription would
    be lost. It returns an async iterator yielding raw payload bytes in
    publish order. Backpressure is implementation-defined; current impls
    bound the per-subscriber buffer and drop oldest on overflow. Caller
    is responsible for cancelling the iterator when done.
    """

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def publish(self, channel: str, payload: bytes) -> None: ...

    async def subscribe(self, channel: str) -> AsyncIterator[bytes]: ...
