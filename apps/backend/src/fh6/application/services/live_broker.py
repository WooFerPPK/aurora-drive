"""Live-stream broker (application service, Phase 9).

Owns the state/cadence/event computation for the live channel and
publishes serialized WS messages onto a `MessageBroker`. The WS adapter
in `interfaces/ws/live.py` subscribes to these channels and runs the
per-connection stride/batch controller + queue.

Splitting this from the WS adapter lets a single ingest worker drive
multiple WS workers (`uvicorn --workers >1`) via Redis pub/sub. The
in-process broker fallback keeps single-worker dev/test working without
Redis.

Channel payloads are JSON bytes; the WS adapter decodes and re-encodes
on its way out (one parse + one stringify per worker per message — cheap
relative to the network round-trip).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Awaitable
from datetime import UTC, datetime
from typing import Any

from fh6.application.services.event_emitter import Event, EventEmitter
from fh6.application.services.session_manager import BoundaryDecision
from fh6.application.services.state_emitter import StateEmitter
from fh6.domain.entities.frame import DecodedFrame
from fh6.domain.ports.messaging import MessageBroker
from fh6.infrastructure.logging import get_logger
from fh6.infrastructure.messaging.inprocess_broker import InProcessBroker
from fh6.infrastructure.telemetry.cadence_meter import CadenceMeter
from fh6.interfaces.ws.heartbeat import TICK_INTERVAL_SECONDS
from fh6.interfaces.ws.wire import serialize_event, serialize_frame, serialize_state

log = get_logger(__name__)

# Per-WS-subscriber outbound queue capacity (drop-oldest on overflow).
# At 60 Hz this is ~1 s of frames — spec §14 / research R-13.
SUBSCRIBER_QUEUE_CAPACITY = 60

CHANNEL_FRAMES = "live:frames"
CHANNEL_STATE = "live:state"
CHANNEL_EVENTS = "live:events"


class LiveBroker:
    """Fan-out producer for `/ws/live`.

    Constructed once per process. Subscribed to by `IngestFrame` via a
    sink callback. On the ingest worker, `on_frame()` runs the cadence
    meter, state emitter, and event emitter, then publishes per-channel
    payloads onto a `MessageBroker`. On every worker (including the
    ingest one), the WS adapter subscribes to the same channels and
    routes per-connection.

    `broker` defaults to a fresh `InProcessBroker`, so tests and
    single-worker dev keep working without explicit wiring. Production
    multi-worker setups inject a `RedisBroker`.
    """

    def __init__(
        self,
        server_name: str = "fh6-backend/0.1.0",
        *,
        broker: MessageBroker | None = None,
        state_emitter: StateEmitter | None = None,
        heartbeat_interval_seconds: float | None = None,
        heartbeat_tick_seconds: float = TICK_INTERVAL_SECONDS,
        broker_tick_seconds: float = 1.0,
        subscriber_queue_capacity: int = SUBSCRIBER_QUEUE_CAPACITY,
    ) -> None:
        self._broker = broker if broker is not None else InProcessBroker()
        self._owns_broker = broker is None
        self._server_name = server_name
        self._state_emitter = state_emitter or StateEmitter()
        self._event_emitter = EventEmitter()
        self._cadence = CadenceMeter()
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._heartbeat_tick_seconds = heartbeat_tick_seconds
        self._broker_tick_seconds = broker_tick_seconds
        self._subscriber_queue_capacity = subscriber_queue_capacity
        self._tick_task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()

    # ---- public accessors used by WS adapter --------------------------

    @property
    def server_name(self) -> str:
        return self._server_name

    @property
    def heartbeat_interval_seconds(self) -> float | None:
        return self._heartbeat_interval_seconds

    @property
    def heartbeat_tick_seconds(self) -> float:
        return self._heartbeat_tick_seconds

    @property
    def subscriber_queue_capacity(self) -> int:
        return self._subscriber_queue_capacity

    def subscribe_frames(self) -> Awaitable[AsyncIterator[bytes]]:
        return self._broker.subscribe(CHANNEL_FRAMES)

    def subscribe_state(self) -> Awaitable[AsyncIterator[bytes]]:
        return self._broker.subscribe(CHANNEL_STATE)

    def subscribe_events(self) -> Awaitable[AsyncIterator[bytes]]:
        return self._broker.subscribe(CHANNEL_EVENTS)

    # ---- ingest sink --------------------------------------------------

    async def on_frame(
        self,
        frame: DecodedFrame,
        decision: BoundaryDecision,
    ) -> None:
        """Called by `IngestFrame` per ingested frame (T059)."""
        self._cadence.observe(frame.raw.timestamp_ms)
        cadence_hz = self._cadence.effective_hz

        state_change = self._state_emitter.on_frame(frame.received_at, cadence_hz)
        boundary_events = self._event_emitter.on_boundary(decision, frame.received_at)
        frame_events = self._event_emitter.on_frame(frame)
        events = boundary_events + frame_events

        envelope: dict[str, Any] = {
            "cadenceHz": cadence_hz,
            "frame": serialize_frame(frame),
        }
        await self._broker.publish(CHANNEL_FRAMES, _encode(envelope))

        if state_change is not None:
            await self._broker.publish(CHANNEL_STATE, _encode(serialize_state(state_change)))

        for ev in events:
            await self._broker.publish(CHANNEL_EVENTS, _encode(serialize_event(ev)))

    async def push_event(self, event: Event) -> None:
        """Inject a one-shot Event onto the live stream.

        Used by emitters that don't ride the per-frame pipeline (e.g.
        the change-point detector — fires from inside the predictor's
        bin-update path, not from `on_frame`).
        """
        await self._broker.publish(CHANNEL_EVENTS, _encode(serialize_event(event)))

    # ---- lifecycle ----------------------------------------------------

    async def start(self) -> None:
        if self._tick_task is not None:
            return
        if self._owns_broker:
            await self._broker.start()
        self._stopped.clear()
        self._tick_task = asyncio.create_task(self._tick_loop(), name="live-broker-tick")

    async def stop(self) -> None:
        self._stopped.set()
        if self._tick_task is not None:
            self._tick_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._tick_task
            self._tick_task = None
        if self._owns_broker:
            await self._broker.stop()

    async def _tick_loop(self) -> None:
        """Drives stream-paused / stream-lost emission. Heartbeat is
        scheduled per-WS by the WS adapter writer task."""
        try:
            while not self._stopped.is_set():
                try:
                    await asyncio.wait_for(
                        self._stopped.wait(),
                        timeout=self._broker_tick_seconds,
                    )
                    return
                except TimeoutError:
                    pass
                # Inner block wrapped so a single transient bug (e.g. a
                # naive/aware datetime regression in StateEmitter) does
                # not kill the task forever.
                try:
                    now = datetime.now(UTC)
                    cadence_hz = self._cadence.effective_hz
                    change = self._state_emitter.on_tick(now, cadence_hz)
                    if change is None:
                        continue
                    await self._broker.publish(CHANNEL_STATE, _encode(serialize_state(change)))
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("live_broker_tick_error")
        except asyncio.CancelledError:
            return


def _encode(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload).encode("utf-8")


__all__ = [
    "CHANNEL_EVENTS",
    "CHANNEL_FRAMES",
    "CHANNEL_STATE",
    "SUBSCRIBER_QUEUE_CAPACITY",
    "LiveBroker",
]
