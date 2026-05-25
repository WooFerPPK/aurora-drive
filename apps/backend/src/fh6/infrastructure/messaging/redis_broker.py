"""Redis `MessageBroker` impl (Phase 9).

Used when `FH6_REDIS_URL` is set. Required for `uvicorn --workers >1`
so subscribers on one worker see frames published from another.

One Redis connection pool is shared for publishes; each `subscribe()`
gets its own `pubsub()` object (Redis pub/sub is stateful — one subscribed
channel per connection in this impl, since fan-out is per-channel and the
WS adapter creates a small fixed number of subscriptions per WS client).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

import redis.asyncio as aioredis
from redis.asyncio.client import PubSub

from fh6.domain.ports.messaging import MessageBroker
from fh6.infrastructure.logging import get_logger

log = get_logger(__name__)


class RedisBroker(MessageBroker):
    def __init__(self, url: str) -> None:
        self._url = url
        self._client: aioredis.Redis | None = None

    async def start(self) -> None:
        if self._client is not None:
            return
        # `decode_responses=False` so payloads stay bytes — JSON-decode
        # happens at the WS adapter, not here.
        self._client = aioredis.from_url(self._url, decode_responses=False)
        # redis-py overloads `ping()` for sync + async clients; the
        # async client returns an awaitable but the stub union confuses
        # mypy. We're definitely in async mode here.
        await self._client.ping()  # type: ignore[misc]
        log.info("redis_broker_connected", url=self._url)

    async def stop(self) -> None:
        if self._client is None:
            return
        await self._client.aclose()
        self._client = None

    async def publish(self, channel: str, payload: bytes) -> None:
        if self._client is None:
            raise RuntimeError("RedisBroker.publish before start()")
        await self._client.publish(channel, payload)

    async def subscribe(self, channel: str) -> AsyncIterator[bytes]:
        if self._client is None:
            raise RuntimeError("RedisBroker.subscribe before start()")
        pubsub = self._client.pubsub()
        await pubsub.subscribe(channel)
        return _RedisSubscription(pubsub, channel)


class _RedisSubscription:
    """Async iterator over a single subscribed Redis channel."""

    def __init__(self, pubsub: PubSub, channel: str) -> None:
        self._pubsub: PubSub | None = pubsub
        self._channel = channel
        self._closed = False

    def __aiter__(self) -> _RedisSubscription:
        return self

    async def __anext__(self) -> bytes:
        if self._closed or self._pubsub is None:
            raise StopAsyncIteration
        pubsub = self._pubsub
        while True:
            # `get_message(timeout=...)` yields control to the loop so a
            # `wait_for(sub.__anext__(), timeout=N)` cancel propagates
            # cleanly. Cancellation interrupts the await but does NOT
            # close the subscription — the subscription stays alive for
            # the next `__anext__` call. Callers must `await sub.aclose()`
            # for real cleanup.
            msg = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            )
            if msg is None:
                continue
            data = msg.get("data")
            if isinstance(data, bytes):
                return data
            if isinstance(data, str):
                return data.encode()
            # Non-payload event — keep looping.

    async def aclose(self) -> None:
        await self._close()

    async def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._pubsub is not None:
            with contextlib.suppress(Exception):
                await self._pubsub.unsubscribe(self._channel)
            with contextlib.suppress(Exception):
                await self._pubsub.aclose()  # type: ignore[no-untyped-call]
            self._pubsub = None
