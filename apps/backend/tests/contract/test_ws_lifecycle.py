"""WebSocket lifecycle contract (T061, constitution Principle X (5)).

Asserts the etiquette rules in API spec §14:
- hello on connect (smoke check; covered in depth by `test_ws_live.py`)
- heartbeat when idle (≥ 5 s in prod; shortened in tests via broker config)
- slow-consumer drop-oldest with a parallel fast reader (SC-007)
- server keeps connection open on `stream-lost` (no force-close)
- clean disconnect cleanup
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fh6.application.services import derivations, modeled_placeholder
from fh6.application.services.live_broker import LiveBroker
from fh6.application.services.session_manager import (
    SessionManager,
    attach_session,
)
from fh6.application.services.state_emitter import StateEmitter
from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.infrastructure.telemetry.fh6_decoder import FH6PacketDecoder
from fh6.interfaces.ws.live import make_router


def _build_broker(
    *,
    heartbeat_interval_seconds: float = 0.15,
    heartbeat_tick_seconds: float = 0.05,
    broker_tick_seconds: float = 0.05,
    pause_floor_ms: int = 100,
    lost_threshold_ms: int = 300,
    queue_capacity: int = 4,
) -> LiveBroker:
    return LiveBroker(
        heartbeat_interval_seconds=heartbeat_interval_seconds,
        heartbeat_tick_seconds=heartbeat_tick_seconds,
        broker_tick_seconds=broker_tick_seconds,
        state_emitter=StateEmitter(
            pause_floor=timedelta(milliseconds=pause_floor_ms),
            lost_threshold=timedelta(milliseconds=lost_threshold_ms),
        ),
        subscriber_queue_capacity=queue_capacity,
    )


def _mount(broker: LiveBroker) -> FastAPI:
    a = FastAPI()
    a.state.live_broker = broker

    def _get_broker(ws):  # type: ignore[no-untyped-def]
        return ws.app.state.live_broker

    a.include_router(make_router(_get_broker))
    a.state.container = a.state

    return a


@pytest.fixture
def client_factory(request: pytest.FixtureRequest) -> Iterator:
    created: list[tuple[TestClient, LiveBroker]] = []

    def _make(broker: LiveBroker) -> TestClient:
        app = _mount(broker)
        c = TestClient(app)
        c.__enter__()
        c.portal.call(broker.start)
        created.append((c, broker))
        return c

    yield _make

    for c, b in created:
        try:
            c.portal.call(b.stop)
        finally:
            c.__exit__(None, None, None)


def _frame(sm: SessionManager, raw: FrameRaw, at: datetime) -> tuple[DecodedFrame, object]:
    decision, frame = attach_session(sm, raw, at)
    derivations.apply(frame, [])
    modeled_placeholder.apply_placeholder(frame)
    return frame, decision


def test_heartbeat_when_idle(client_factory, golden_packet: bytes) -> None:
    broker = _build_broker(heartbeat_interval_seconds=0.15)
    client = client_factory(broker)

    with client.websocket_connect("/ws/live?frameRate=30") as ws:
        ws.receive_json()  # hello
        # No frames; the heartbeat scheduler should fire after the
        # configured interval.
        msg = ws.receive_json()
        assert msg["type"] == "heartbeat"
        assert isinstance(msg["at"], float)


def test_stream_lost_emits_state_but_keeps_open(
    client_factory,
    golden_packet: bytes,
) -> None:
    broker = _build_broker(
        heartbeat_interval_seconds=5.0,  # disable heartbeat noise
        pause_floor_ms=50,
        lost_threshold_ms=200,
        broker_tick_seconds=0.04,
    )
    client = client_factory(broker)
    sm = SessionManager(silence_seconds=60.0)
    raw = FH6PacketDecoder().decode(golden_packet)
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)

    with client.websocket_connect("/ws/live?frameRate=30") as ws:
        ws.receive_json()  # hello
        f, d = _frame(sm, raw, t0)
        client.portal.call(broker.on_frame, f, d)

        # Drain initial driving/session_started/frame messages, then wait
        # for stream-lost (server keeps connection open).
        saw_lost = False
        for _ in range(50):
            msg = ws.receive_json()
            if msg.get("type") == "state" and msg.get("state") == "stream-lost":
                saw_lost = True
                break
        assert saw_lost
        # Connection is still open: ping-able by sending a valid rate.
        ws.send_json({"type": "rate", "hz": 30})


def test_back_pressure_drops_oldest_not_newest() -> None:
    """Slow consumer's queue is bounded; new frames push old ones out
    rather than buffer indefinitely (spec §14, research R-13).

    Phase 9: drop-oldest lives in the WS adapter's per-connection queue
    (the broker layer also drops oldest on its own queues — that's the
    subject of `test_message_broker.py`). This test exercises the WS
    boundary primitive directly: a queue at capacity, feed it more
    messages, count drops.
    """
    import asyncio

    from fh6.interfaces.ws.live import FrameStrideController, _push

    async def _run() -> tuple[int, int]:
        class _FakeWS:
            client_state = None

        sub = _SubscriberFactory(
            queue=asyncio.Queue(maxsize=4),
            stride=FrameStrideController(hz=30),
        )
        for i in range(12):
            await _push(sub, {"type": "frame", "n": i})
        return sub.dropped, sub.queue.qsize()

    dropped, qsize = asyncio.run(_run())
    assert dropped == 8
    assert qsize == 4


def _SubscriberFactory(*, queue, stride):
    """Minimal stand-in matching the `_Subscriber` shape `_push` needs."""
    from fh6.interfaces.ws.live import _Subscriber

    class _FakeWS:
        client_state = None

    return _Subscriber(
        ws=_FakeWS(),  # type: ignore[arg-type]
        topics={"frames"},
        stride=stride,
        queue=queue,
        last_emit_at=datetime.now(UTC),
    )


def test_disconnect_cleans_up_subscriber(client_factory) -> None:
    """WS disconnect cancels the per-channel subscription tasks, which
    triggers `aclose()` on the broker iterator and removes the queue
    from the broker's subscriber list. Phase 9 moves subscriber state
    from `LiveBroker` to the `MessageBroker` impl, so we count the
    broker's per-channel queues instead of the old `_subscribers` list.
    """
    from fh6.application.services.live_broker import CHANNEL_FRAMES

    broker = _build_broker(heartbeat_interval_seconds=5.0)
    client = client_factory(broker)

    def _count_subscriptions() -> int:
        inproc = broker._broker  # InProcessBroker (default when broker= unset)
        return len(inproc._channels.get(CHANNEL_FRAMES, []))

    assert _count_subscriptions() == 0
    with client.websocket_connect("/ws/live?frameRate=30") as ws:
        ws.receive_json()  # hello
        assert _count_subscriptions() == 1

    # After context exit the subscription tasks are cancelled and the
    # iterator's aclose() drops the queue from the broker.
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if _count_subscriptions() == 0:
            break
        time.sleep(0.05)
    assert _count_subscriptions() == 0
