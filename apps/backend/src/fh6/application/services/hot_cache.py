"""Per-(session, car) rolling window of recent frames (research R-5).

Phase 9: optionally mirror writes across uvicorn workers via a
`MessageBroker`. Every worker keeps its own in-process cache for rAF-hot
reads. On `append` / `drop_session` / `evict_after`, the change is also
published to a broker channel; every worker's subscriber loop applies
the change to its local copy, except for messages it published itself
(filtered by `origin_id`) — that preserves read-after-write consistency
for downstream ingest sinks on the publishing worker.

Cross-worker payloads are pickle, since `DecodedFrame` is a deeply
nested dataclass with non-JSON types (datetime, Enum, UUID) and all
workers run the same Python interpreter against the same codebase
(uvicorn forks). For a future cross-language consumer, swap to a typed
JSON wire format.
"""

from __future__ import annotations

import asyncio
import contextlib
import pickle
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from fh6.domain.entities.frame import DecodedFrame
from fh6.domain.ports.messaging import MessageBroker
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.infrastructure.logging import get_logger

log = get_logger(__name__)

CHANNEL_HOTCACHE = "hotcache:writes"


@dataclass(slots=True)
class HotFrameWindow:
    latest: DecodedFrame | None = None
    window: deque[DecodedFrame] = field(default_factory=lambda: deque(maxlen=180))  # ~3s @ 60Hz


class HotCache:
    """Process-local hot cache, optionally pub/sub-mirrored across workers.

    Without `broker`, behaves identically to the pre-Phase-9 HotCache.
    With `broker`, every mutating operation publishes to a shared
    channel; the subscriber loop on each worker applies remote updates
    to keep all workers' copies in lockstep.
    """

    def __init__(
        self,
        broker: MessageBroker | None = None,
        *,
        origin_id: str | None = None,
    ) -> None:
        self._by_key: dict[tuple[SessionId, CarId], HotFrameWindow] = {}
        self._broker = broker
        self._origin_id = origin_id or uuid4().hex
        self._sub_task: asyncio.Task[None] | None = None
        self._publish_tasks: set[asyncio.Task[None]] = set()

    # ---- public mutators ----------------------------------------------

    def append(self, frame: DecodedFrame) -> None:
        if frame.session_id is None:
            return
        self._apply_append(frame)
        self._publish({"op": "append", "frame": frame})

    def drop_session(self, session_id: SessionId) -> None:
        self._apply_drop_session(session_id)
        self._publish({"op": "drop_session", "session_id": session_id})

    def evict_after(self, session_id: SessionId, threshold_time: datetime) -> None:
        self._apply_evict_after(session_id, threshold_time)
        self._publish(
            {
                "op": "evict_after",
                "session_id": session_id,
                "threshold_time": threshold_time,
            }
        )

    # ---- public readers -----------------------------------------------

    def latest_for(self, session_id: SessionId, car_id: CarId) -> DecodedFrame | None:
        w = self._by_key.get((session_id, car_id))
        return w.latest if w is not None else None

    def window_for(
        self, session_id: SessionId, car_id: CarId, lookback: timedelta | None = None
    ) -> list[DecodedFrame]:
        w = self._by_key.get((session_id, car_id))
        if w is None:
            return []
        if lookback is None:
            return list(w.window)
        if w.latest is None:
            return []
        cutoff = w.latest.received_at - lookback
        return [f for f in w.window if f.received_at >= cutoff]

    def __len__(self) -> int:
        return len(self._by_key)

    # ---- lifecycle ----------------------------------------------------

    async def start(self) -> None:
        if self._broker is None or self._sub_task is not None:
            return
        self._sub_task = asyncio.create_task(self._subscribe_loop(), name="hot-cache-sub")

    async def stop(self) -> None:
        if self._sub_task is not None:
            self._sub_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sub_task
            self._sub_task = None
        # Drain any pending publishes so the broker isn't called after stop().
        pending = list(self._publish_tasks)
        for t in pending:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t

    # ---- internal apply (no publish) ----------------------------------

    def _apply_append(self, frame: DecodedFrame) -> None:
        if frame.session_id is None:
            return
        key = (frame.session_id, frame.car_id)
        w = self._by_key.get(key)
        if w is None:
            w = HotFrameWindow()
            self._by_key[key] = w
        w.latest = frame
        w.window.append(frame)

    def _apply_drop_session(self, session_id: SessionId) -> None:
        for key in [k for k in self._by_key if k[0] == session_id]:
            del self._by_key[key]

    def _apply_evict_after(self, session_id: SessionId, threshold_time: datetime) -> None:
        for key in list(self._by_key.keys()):
            if key[0] != session_id:
                continue
            w = self._by_key[key]
            kept = [f for f in w.window if f.received_at <= threshold_time]
            w.window.clear()
            w.window.extend(kept)
            w.latest = kept[-1] if kept else None

    # ---- publish + subscribe ------------------------------------------

    def _publish(self, msg: dict[str, Any]) -> None:
        """Schedule an async publish on the running loop. No-op without a
        broker or when there's no event loop (sync-test usage)."""
        if self._broker is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        msg["origin"] = self._origin_id
        coro = self._publish_one(msg)
        task = loop.create_task(coro)
        self._publish_tasks.add(task)
        task.add_done_callback(self._publish_tasks.discard)

    async def _publish_one(self, msg: dict[str, Any]) -> None:
        if self._broker is None:
            return
        try:
            payload = pickle.dumps(msg, protocol=pickle.HIGHEST_PROTOCOL)
            await self._broker.publish(CHANNEL_HOTCACHE, payload)
        except Exception:
            log.exception("hot_cache_publish_failed", op=msg.get("op"))

    async def _subscribe_loop(self) -> None:
        if self._broker is None:
            return
        try:
            sub: AsyncIterator[bytes] = await self._broker.subscribe(CHANNEL_HOTCACHE)
            try:
                async for raw in sub:
                    try:
                        msg = pickle.loads(raw)
                    except Exception:
                        log.exception("hot_cache_decode_failed")
                        continue
                    # Skip own publishes — local apply already happened
                    # synchronously inside the mutator.
                    if msg.get("origin") == self._origin_id:
                        continue
                    op = msg.get("op")
                    if op == "append":
                        self._apply_append(msg["frame"])
                    elif op == "drop_session":
                        self._apply_drop_session(msg["session_id"])
                    elif op == "evict_after":
                        self._apply_evict_after(msg["session_id"], msg["threshold_time"])
                    else:
                        log.warning("hot_cache_unknown_op", op=op)
            finally:
                aclose = getattr(sub, "aclose", None)
                if aclose is not None:
                    with contextlib.suppress(Exception):
                        await aclose()
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("hot_cache_subscribe_failed")
