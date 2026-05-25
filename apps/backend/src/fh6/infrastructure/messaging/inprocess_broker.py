"""In-process `MessageBroker` impl.

Default broker when `FH6_REDIS_URL` is unset. Backed by per-subscriber
`asyncio.Queue`s with drop-oldest backpressure (bounded buffer matches
the WS subscriber capacity at the next ring out, so a single slow
subscriber cannot stall publishers).

Single-process only; multi-worker uvicorn must use `RedisBroker`.

asyncio is cooperative within one event loop, so subscriber registration
needs no lock — dict / list mutations between `await` points are atomic.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict
from collections.abc import AsyncIterator, Callable

from fh6.domain.ports.messaging import MessageBroker

DEFAULT_QUEUE_CAPACITY = 256


class InProcessBroker(MessageBroker):
    def __init__(self, *, queue_capacity: int = DEFAULT_QUEUE_CAPACITY) -> None:
        self._queue_capacity = queue_capacity
        self._channels: dict[str, list[asyncio.Queue[bytes]]] = defaultdict(list)

    async def start(self) -> None:  # no-op; kept for port symmetry
        return

    async def stop(self) -> None:
        for queues in self._channels.values():
            for q in queues:
                while not q.empty():
                    with contextlib.suppress(asyncio.QueueEmpty):
                        q.get_nowait()
        self._channels.clear()

    async def publish(self, channel: str, payload: bytes) -> None:
        for q in list(self._channels.get(channel, ())):
            if q.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()
            await q.put(payload)

    async def subscribe(self, channel: str) -> AsyncIterator[bytes]:
        q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=self._queue_capacity)
        self._channels[channel].append(q)
        return _SubscriptionIterator(q, on_close=lambda: self._drop(channel, q))

    def _drop(self, channel: str, q: asyncio.Queue[bytes]) -> None:
        if q in self._channels.get(channel, ()):
            self._channels[channel].remove(q)


class _SubscriptionIterator:
    """Async iterator wrapping an asyncio.Queue with explicit cleanup.

    Cancellation of an `__anext__()` only interrupts the current await —
    it does NOT close the iterator. That keeps timeout-style patterns
    (`asyncio.wait_for(sub.__anext__(), timeout=N)`) usable: the
    subscription stays alive across timeouts. Callers are expected to
    `await sub.aclose()` (or use a `finally` block) when they're really
    done with the subscription.
    """

    def __init__(
        self,
        queue: asyncio.Queue[bytes],
        *,
        on_close: Callable[[], None],
    ) -> None:
        self._queue = queue
        self._on_close = on_close
        self._closed = False

    def __aiter__(self) -> _SubscriptionIterator:
        return self

    async def __anext__(self) -> bytes:
        if self._closed:
            raise StopAsyncIteration
        return await self._queue.get()

    async def aclose(self) -> None:
        self._close()

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._on_close()
