"""`/ws/coach` WebSocket adapter (Phase 9 refactor).

Thin WS wrapper: subscribes to the coach callouts channel exposed by
`application.services.coach_broker.CoachBroker` and forwards to the
connected WS client. Per-connection drop-oldest queue + heartbeat.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect, WebSocketState

from fh6.application.services.coach_broker import (
    SUBSCRIBER_QUEUE_CAPACITY,
    CoachBroker,
)
from fh6.infrastructure.logging import get_logger
from fh6.interfaces.ws.heartbeat import run_heartbeat
from fh6.interfaces.ws.wire import heartbeat_message

log = get_logger(__name__)


@dataclass(slots=True)
class _CoachSubscriber:
    ws: WebSocket
    queue: asyncio.Queue[dict[str, object]]
    last_emit_at: datetime
    stop: asyncio.Event = field(default_factory=asyncio.Event)


async def _push(sub: _CoachSubscriber, msg: dict[str, object]) -> None:
    if sub.queue.full():
        with contextlib.suppress(asyncio.QueueEmpty):
            sub.queue.get_nowait()
    await sub.queue.put(msg)


async def _writer(sub: _CoachSubscriber) -> None:
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
    except (WebSocketDisconnect, asyncio.CancelledError):
        return


async def _callouts_consumer(
    sub: _CoachSubscriber,
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


def make_router(get_broker: Callable[[WebSocket], CoachBroker]) -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws/coach")
    async def ws_coach(websocket: WebSocket) -> None:
        broker = get_broker(websocket)
        await websocket.accept()

        # Subscribe before sending hello (same race-avoidance reason as
        # the live adapter).
        sub = _CoachSubscriber(
            ws=websocket,
            queue=asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_CAPACITY),
            last_emit_at=datetime.now(UTC),
        )
        callouts_iter = await broker.subscribe_callouts()

        availability = await broker.availability.status()
        hello = {
            "type": "hello",
            "server": broker.server_name,
            "coach": {
                "available": availability.available,
                "reason": availability.reason,
                "model": availability.model,
            },
        }
        await websocket.send_text(json.dumps(hello))

        writer_task = asyncio.create_task(_writer(sub), name="coach-ws-writer")
        callouts_task = asyncio.create_task(
            _callouts_consumer(sub, callouts_iter), name="coach-ws-callouts"
        )

        async def emit_heartbeat(now: datetime) -> None:
            await sub.queue.put(heartbeat_message(now))

        hb_task = asyncio.create_task(
            run_heartbeat(
                last_emit_at=lambda: sub.last_emit_at,
                emit=emit_heartbeat,
                stop=sub.stop,
                tick_seconds=broker.heartbeat_tick_seconds,
                heartbeat_interval_seconds=broker.heartbeat_interval_seconds,
            ),
            name="coach-ws-heartbeat",
        )

        try:
            while True:
                try:
                    text = await websocket.receive_text()
                except WebSocketDisconnect:
                    return
                try:
                    json.loads(text)
                except json.JSONDecodeError:
                    await websocket.close(code=1003, reason="malformed-json")
                    return
        finally:
            sub.stop.set()
            for t in (writer_task, callouts_task, hb_task):
                t.cancel()
            for t in (writer_task, callouts_task, hb_task):
                with contextlib.suppress(asyncio.CancelledError):
                    await t
            if websocket.client_state != WebSocketState.DISCONNECTED:
                with contextlib.suppress(Exception):  # pragma: no cover
                    await websocket.close()

    return router


__all__ = ["SUBSCRIBER_QUEUE_CAPACITY", "make_router"]
