"""`/ws/live` WebSocket adapter (Phase 9 refactor).

Thin WS wrapper: per-connection topic filter, downsampling, drop-oldest
queue, heartbeat. Subscribes to the live channels exposed by
`application.services.live_broker.LiveBroker` (which itself rides on a
`MessageBroker` port — in-process by default, Redis when configured).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from fh6.application.services.live_broker import (
    SUBSCRIBER_QUEUE_CAPACITY,
    LiveBroker,
)
from fh6.infrastructure.logging import get_logger
from fh6.interfaces.ws.heartbeat import HEARTBEAT_INTERVAL, run_heartbeat
from fh6.interfaces.ws.wire import heartbeat_message, hello_message

log = get_logger(__name__)

ALLOWED_RATES: frozenset[int] = frozenset({10, 30, 60})
ALLOWED_TOPICS_LIVE: frozenset[str] = frozenset({"frames", "events"})

BATCH_THRESHOLD_HZ = 30
BATCH_MAX_FRAMES = 4


class FrameStrideController:
    """Per-WS-subscriber stride + batch controller on serialized frames.

    Operates on the pre-serialized frame dicts that come off the broker
    channel — keeps DecodedFrame off the WS-adapter side of the boundary.
    """

    def __init__(self, hz: int = 30) -> None:
        self._hz = hz
        self._counter = 0
        self._buffer: list[dict[str, Any]] = []

    @property
    def hz(self) -> int:
        return self._hz

    def set_rate(self, hz: int) -> None:
        if hz not in ALLOWED_RATES:
            raise ValueError(f"unsupported hz: {hz!r}")
        self._hz = hz
        self._counter = 0
        self._buffer.clear()

    def _stride_for(self, cadence_hz: float | None) -> int:
        if cadence_hz is None or cadence_hz <= self._hz:
            return 1
        ratio = cadence_hz / float(self._hz)
        return max(1, round(ratio))

    def offer(
        self,
        frame_msg: dict[str, Any],
        cadence_hz: float | None,
    ) -> dict[str, Any] | None:
        """Returns the WS payload to send (single frame or batch), or
        None to skip this frame."""
        stride = self._stride_for(cadence_hz)
        self._counter += 1
        if self._counter < stride:
            return None
        self._counter = 0

        if self._hz > BATCH_THRESHOLD_HZ:
            self._buffer.append(frame_msg)
            if len(self._buffer) >= BATCH_MAX_FRAMES:
                batch = self._buffer
                self._buffer = []
                return {"type": "frames", "batch": batch}
            return None
        return frame_msg


@dataclass(slots=True)
class _Subscriber:
    ws: WebSocket
    topics: set[str]
    stride: FrameStrideController
    queue: asyncio.Queue[dict[str, Any]]
    last_emit_at: datetime
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    dropped: int = 0


async def _push(sub: _Subscriber, msg: dict[str, Any]) -> None:
    """Enqueue with drop-oldest on overflow (spec §14 / research R-13)."""
    if sub.queue.full():
        with contextlib.suppress(asyncio.QueueEmpty):
            sub.queue.get_nowait()
            sub.dropped += 1
    await sub.queue.put(msg)


async def _writer(sub: _Subscriber) -> None:
    try:
        while not sub.stop.is_set():
            try:
                msg = await asyncio.wait_for(sub.queue.get(), timeout=0.5)
            except TimeoutError:
                continue
            if sub.ws.client_state != WebSocketState.CONNECTED:
                return
            await sub.ws.send_text(json.dumps(msg))
            sub.last_emit_at = datetime.now(UTC)
    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        return
    except Exception:
        log.exception("live_ws_writer_error")
        return


async def _frames_consumer(
    sub: _Subscriber,
    sub_iter: AsyncIterator[bytes],
) -> None:
    try:
        async for raw in sub_iter:
            if "frames" not in sub.topics:
                continue
            envelope = json.loads(raw)
            cadence_hz = envelope.get("cadenceHz")
            frame_msg = envelope.get("frame")
            if frame_msg is None:
                continue
            out = sub.stride.offer(frame_msg, cadence_hz)
            if out is not None:
                await _push(sub, out)
    except asyncio.CancelledError:
        return
    finally:
        with contextlib.suppress(Exception):
            await sub_iter.aclose()  # type: ignore[attr-defined]


async def _state_consumer(
    sub: _Subscriber,
    sub_iter: AsyncIterator[bytes],
) -> None:
    try:
        async for raw in sub_iter:
            msg = json.loads(raw)
            await _push(sub, msg)
    except asyncio.CancelledError:
        return
    finally:
        with contextlib.suppress(Exception):
            await sub_iter.aclose()  # type: ignore[attr-defined]


async def _events_consumer(
    sub: _Subscriber,
    sub_iter: AsyncIterator[bytes],
) -> None:
    try:
        async for raw in sub_iter:
            if "events" not in sub.topics:
                continue
            msg = json.loads(raw)
            await _push(sub, msg)
    except asyncio.CancelledError:
        return
    finally:
        with contextlib.suppress(Exception):
            await sub_iter.aclose()  # type: ignore[attr-defined]


def make_router(get_broker: Callable[[WebSocket], LiveBroker]) -> APIRouter:
    """Mount the live router with broker access provided by `app.state`.

    The factory pattern keeps the WS endpoint testable: tests can mount
    the same handler against an in-memory broker.
    """
    router = APIRouter()

    @router.websocket("/ws/live")
    async def ws_live(
        websocket: WebSocket,
        sessionId: str = Query(default="auto"),
        car: str = Query(default="current"),
        frameRate: int = Query(default=30, alias="frameRate"),
    ) -> None:
        broker = get_broker(websocket)

        if frameRate not in ALLOWED_RATES:
            await websocket.close(
                code=1008,
                reason=(f"unsupported frameRate={frameRate}; allowed={sorted(ALLOWED_RATES)}"),
            )
            return

        await websocket.accept()

        # Subscribe to broker channels BEFORE sending hello — the test
        # pattern is `receive(hello); publish(frame); receive(frame)`,
        # so the subscription must be registered before the test sees
        # hello, or the publish would race the subscribe.
        sub = _Subscriber(
            ws=websocket,
            topics=set(ALLOWED_TOPICS_LIVE),
            stride=FrameStrideController(hz=frameRate),
            queue=asyncio.Queue(maxsize=broker.subscriber_queue_capacity),
            last_emit_at=datetime.now(UTC),
        )

        frames_iter = await broker.subscribe_frames()
        state_iter = await broker.subscribe_state()
        events_iter = await broker.subscribe_events()

        await websocket.send_text(json.dumps(hello_message(broker.server_name)))

        # One-shot bind-failed notice for the UDP listener (mirrors the
        # Tauri client's `udp_bind_failed` event).
        telemetry_health = getattr(websocket.app.state, "telemetry_health", None)
        if telemetry_health is not None and telemetry_health.bind_error:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "udp_bind_failed",
                        "message": telemetry_health.bind_error,
                    }
                )
            )

        writer_task = asyncio.create_task(_writer(sub), name="live-ws-writer")
        frames_task = asyncio.create_task(_frames_consumer(sub, frames_iter), name="live-ws-frames")
        state_task = asyncio.create_task(_state_consumer(sub, state_iter), name="live-ws-state")
        events_task = asyncio.create_task(_events_consumer(sub, events_iter), name="live-ws-events")

        async def emit_heartbeat(now: datetime) -> None:
            await _push(sub, heartbeat_message(now))

        hb_kwargs: dict[str, Any] = {
            "last_emit_at": lambda: sub.last_emit_at,
            "emit": emit_heartbeat,
            "stop": sub.stop,
            "tick_seconds": broker.heartbeat_tick_seconds,
        }
        if broker.heartbeat_interval_seconds is not None:
            hb_kwargs["heartbeat_interval_seconds"] = broker.heartbeat_interval_seconds
        hb_task = asyncio.create_task(
            run_heartbeat(**hb_kwargs),
            name="live-ws-heartbeat",
        )

        try:
            while True:
                try:
                    text = await websocket.receive_text()
                except WebSocketDisconnect:
                    return
                try:
                    msg = json.loads(text)
                except json.JSONDecodeError:
                    await websocket.close(code=1003, reason="malformed-json")
                    return
                kind = msg.get("type")
                if kind == "subscribe":
                    raw_topics = msg.get("topics") or []
                    topics: set[str] = set()
                    bad: list[str] = []
                    for t in raw_topics:
                        if t == "coach":
                            await websocket.send_text(
                                json.dumps(
                                    {
                                        "type": "error",
                                        "code": "wrong-channel",
                                        "message": "coach topic is served by /ws/coach",
                                    }
                                )
                            )
                            return
                        if t in ALLOWED_TOPICS_LIVE:
                            topics.add(t)
                        else:
                            bad.append(t)
                    if bad:
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "error",
                                    "code": "unknown-topic",
                                    "topics": bad,
                                }
                            )
                        )
                    if topics:
                        sub.topics = topics
                elif kind == "rate":
                    hz = msg.get("hz")
                    if hz in ALLOWED_RATES:
                        sub.stride.set_rate(int(hz))
                    else:
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "error",
                                    "code": "unsupported-rate",
                                    "hz": hz,
                                }
                            )
                        )
                else:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "error",
                                "code": "unknown-message",
                                "received": kind,
                            }
                        )
                    )
        finally:
            sub.stop.set()
            for t in (writer_task, frames_task, state_task, events_task, hb_task):
                t.cancel()
            for t in (writer_task, frames_task, state_task, events_task, hb_task):
                with contextlib.suppress(asyncio.CancelledError):
                    await t
            if websocket.client_state != WebSocketState.DISCONNECTED:
                with contextlib.suppress(Exception):  # pragma: no cover
                    await websocket.close()

    return router


__all__ = [
    "ALLOWED_RATES",
    "ALLOWED_TOPICS_LIVE",
    "BATCH_MAX_FRAMES",
    "BATCH_THRESHOLD_HZ",
    "HEARTBEAT_INTERVAL",
    "SUBSCRIBER_QUEUE_CAPACITY",
    "FrameStrideController",
    "make_router",
]
