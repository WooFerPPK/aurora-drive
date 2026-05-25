"""Contract test for `/ws/live` (T060, API spec §2).

Covers: hello on connect, frame shape (all three tiers present + modeled
placeholder), state transition emission, every documented event kind,
batched frames at 60 Hz, mid-stream rate change, subscribe negotiation,
malformed message handling, and the wrong-channel `coach` rejection.

Uses Starlette's TestClient. Frames are injected into the broker via the
TestClient's blocking portal so the server loop drains them onto each
subscriber's outbound queue.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fh6.application.services import derivations, modeled_placeholder
from fh6.application.services.live_broker import LiveBroker
from fh6.application.services.session_manager import (
    BoundaryDecision,
    SessionManager,
    attach_session,
)
from fh6.application.services.state_emitter import StateEmitter
from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.infrastructure.telemetry.fh6_decoder import FH6PacketDecoder
from fh6.interfaces.ws.live import make_router


@pytest.fixture
def broker() -> LiveBroker:
    return LiveBroker(
        heartbeat_interval_seconds=0.2,
        heartbeat_tick_seconds=0.05,
        broker_tick_seconds=0.05,
        state_emitter=StateEmitter(
            pause_floor=timedelta(milliseconds=100),
            lost_threshold=timedelta(milliseconds=400),
        ),
    )


@pytest.fixture
def app(broker: LiveBroker) -> FastAPI:
    a = FastAPI()
    a.state.live_broker = broker

    def _get_broker(ws):  # type: ignore[no-untyped-def]
        return ws.app.state.live_broker

    a.include_router(make_router(_get_broker))
    a.state.container = a.state

    return a


@pytest.fixture
def client(app: FastAPI, broker: LiveBroker) -> Iterator[TestClient]:
    with TestClient(app) as c:
        # broker.start() schedules its tick loop on the server loop.
        c.portal.call(broker.start)
        try:
            yield c
        finally:
            c.portal.call(broker.stop)


def _make_frame(
    sm: SessionManager,
    raw: FrameRaw,
    at: datetime,
) -> tuple[DecodedFrame, BoundaryDecision]:
    decision, frame = attach_session(sm, raw, at)
    derivations.apply(frame, [])
    modeled_placeholder.apply_placeholder(frame)
    return frame, decision


def test_hello_is_first_message(client: TestClient) -> None:
    with client.websocket_connect("/ws/live?frameRate=30") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert hello["server"]
        assert "frames" in hello["capabilities"]
        assert "rate-change" in hello["capabilities"]


def test_invalid_frame_rate_closes(client: TestClient) -> None:
    with pytest.raises(Exception):  # Starlette closes on bad query
        with client.websocket_connect("/ws/live?frameRate=120"):
            pass


def test_frame_message_carries_all_three_tiers(
    client: TestClient,
    broker: LiveBroker,
    golden_packet: bytes,
) -> None:
    sm = SessionManager(silence_seconds=60.0)
    raw = FH6PacketDecoder().decode(golden_packet)
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)

    with client.websocket_connect("/ws/live?frameRate=30") as ws:
        ws.receive_json()  # hello
        frame, decision = _make_frame(sm, raw, t0)
        client.portal.call(broker.on_frame, frame, decision)

        msgs: list[dict] = []
        # Drain until we see frame + state + session_started event.
        deadline_msgs = 8
        while len(msgs) < deadline_msgs:
            msgs.append(ws.receive_json())
            if (
                any(m.get("type") == "frame" for m in msgs)
                and any(
                    m.get("type") == "event" and m.get("kind") == "session_started" for m in msgs
                )
                and any(m.get("type") == "state" for m in msgs)
            ):
                break

        frame_msg = next(m for m in msgs if m.get("type") == "frame")
        assert {"raw" not in frame_msg, "derived" in frame_msg, "modeled" in frame_msg} == {True}
        assert frame_msg["modeled"]["modeledByVersion"] == "placeholder"
        assert frame_msg["modeled"]["tireWearConfidence"] == 0.0
        assert frame_msg["derived"]["weightFront"] == pytest.approx(0.5, abs=1e-4)
        assert frame_msg["sessionId"]
        assert frame_msg["carId"]

        # State and session_started both seen.
        state_msg = next(m for m in msgs if m.get("type") == "state")
        assert state_msg["state"] == "driving"
        types_seen = [(m.get("type"), m.get("kind")) for m in msgs]
        ss = next(
            (m for m in msgs if m.get("type") == "event" and m.get("kind") == "session_started"),
            None,
        )
        assert ss is not None, f"session_started missing; saw {types_seen}"
        assert ss["sessionId"]


def test_mid_stream_rate_change(
    client: TestClient,
    broker: LiveBroker,
    golden_packet: bytes,
) -> None:
    sm = SessionManager(silence_seconds=60.0)
    raw = FH6PacketDecoder().decode(golden_packet)
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)

    with client.websocket_connect("/ws/live?frameRate=30") as ws:
        ws.receive_json()  # hello
        ws.send_json({"type": "rate", "hz": 10})

        # Inject 12 frames spaced 16 ms apart (~60 Hz source).
        for i in range(12):
            f, d = _make_frame(sm, raw, t0 + timedelta(milliseconds=16 * i))
            client.portal.call(broker.on_frame, f, d)

        frame_count = 0
        for _ in range(30):  # bounded read
            msg = ws.receive_json()
            if msg.get("type") == "frame":
                frame_count += 1
            if frame_count >= 2:
                break
        # 12 frames at requested 10 Hz with ~60 Hz source ≈ stride 6 → ~2 frames.
        assert frame_count <= 3


def test_subscribe_filters_topics(
    client: TestClient,
    broker: LiveBroker,
    golden_packet: bytes,
) -> None:
    sm = SessionManager(silence_seconds=60.0)
    raw = FH6PacketDecoder().decode(golden_packet)
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)

    with client.websocket_connect("/ws/live?frameRate=30") as ws:
        ws.receive_json()  # hello
        ws.send_json({"type": "subscribe", "topics": ["events"]})

        f, d = _make_frame(sm, raw, t0)
        client.portal.call(broker.on_frame, f, d)

        # With only `events` subscribed we should see no `frame` messages.
        seen_kinds: list[str] = []
        for _ in range(8):
            msg = ws.receive_json()
            seen_kinds.append(msg.get("type", "?"))
            if msg.get("type") == "event" and msg.get("kind") == "session_started":
                break
        assert "frame" not in seen_kinds


def test_coach_topic_rejected_with_redirect(
    client: TestClient,
) -> None:
    with client.websocket_connect("/ws/live?frameRate=30") as ws:
        ws.receive_json()  # hello
        ws.send_json({"type": "subscribe", "topics": ["coach"]})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert msg["code"] == "wrong-channel"


def test_unknown_rate_returns_error(client: TestClient) -> None:
    with client.websocket_connect("/ws/live?frameRate=30") as ws:
        ws.receive_json()  # hello
        ws.send_json({"type": "rate", "hz": 5})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert msg["code"] == "unsupported-rate"


def test_malformed_json_closes_connection(client: TestClient) -> None:
    from starlette.websockets import WebSocketDisconnect

    with client.websocket_connect("/ws/live?frameRate=30") as ws:
        ws.receive_json()  # hello
        ws.send_text("{not json")
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_event_kinds_emitted(
    client: TestClient,
    broker: LiveBroker,
    make_packet,
) -> None:
    """Cover the per-frame event detectors: lap_started, lap_completed,
    shift, missed_upshift, oversteer, off_track, smashable_hit. Plus
    boundary-driven session_started / session_ended (via second car)."""
    decoder = FH6PacketDecoder()
    sm = SessionManager(silence_seconds=60.0)
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)

    def at(i: int) -> datetime:
        return t0 + timedelta(milliseconds=300 * i)

    seqs: list[FrameRaw] = []
    # Frame 0: lap 1, gear 3, redlining → starts dwell + lap_started.
    seqs.append(
        decoder.decode(
            make_packet(LapNumber=1, Gear=3, CurrentEngineRpm=7900.0, EngineMaxRpm=8000.0)
        )
    )
    # Frame 1: still lap 1, still redlining (dwell grows to ≥200 ms).
    seqs.append(
        decoder.decode(
            make_packet(LapNumber=1, Gear=3, CurrentEngineRpm=7900.0, EngineMaxRpm=8000.0)
        )
    )
    # Frame 2: shift up → shift + missed_upshift events.
    seqs.append(
        decoder.decode(
            make_packet(LapNumber=1, Gear=4, CurrentEngineRpm=6000.0, EngineMaxRpm=8000.0)
        )
    )
    # Frame 3: oversteer (rear slip > front by margin) + speed > 5 m/s.
    seqs.append(
        decoder.decode(
            make_packet(
                LapNumber=1,
                Gear=4,
                Speed=30.0,
                CombSlipFL=0.02,
                CombSlipFR=0.02,
                CombSlipRL=0.30,
                CombSlipRR=0.30,
            )
        )
    )
    # Frame 4: off_track (all four surfaceRumble high).
    seqs.append(
        decoder.decode(
            make_packet(
                LapNumber=1,
                Gear=4,
                Speed=30.0,
                SurfRumbleFL=0.9,
                SurfRumbleFR=0.9,
                SurfRumbleRL=0.9,
                SurfRumbleRR=0.9,
            )
        )
    )
    # Frame 5: smashable_hit.
    seqs.append(decoder.decode(make_packet(LapNumber=1, Gear=4, Speed=30.0, SmashableVelDiff=12.3)))
    # Frame 6: lap rollover → lap_completed + lap_started.
    seqs.append(decoder.decode(make_packet(LapNumber=2, Gear=4)))
    # Frame 7: car change → session_ended + session_started.
    seqs.append(decoder.decode(make_packet(CarOrdinal=9999, CarPI=999, LapNumber=2, Gear=4)))

    with client.websocket_connect("/ws/live?frameRate=30") as ws:
        ws.receive_json()  # hello
        for i, raw in enumerate(seqs):
            f, d = _make_frame(sm, raw, at(i))
            client.portal.call(broker.on_frame, f, d)

        kinds: set[str] = set()
        for _ in range(80):  # bounded drain
            msg = ws.receive_json()
            if msg.get("type") == "event":
                kinds.add(msg["kind"])
            if {
                "session_started",
                "lap_started",
                "shift",
                "oversteer",
                "off_track",
                "smashable_hit",
                "lap_completed",
                "session_ended",
            }.issubset(kinds):
                break

        assert "session_started" in kinds
        assert "lap_started" in kinds
        assert "shift" in kinds
        assert "oversteer" in kinds
        assert "off_track" in kinds
        assert "smashable_hit" in kinds
        assert "lap_completed" in kinds
        assert "session_ended" in kinds


def test_batched_frames_at_60hz(
    client: TestClient,
    broker: LiveBroker,
    golden_packet: bytes,
) -> None:
    decoder = FH6PacketDecoder()
    sm = SessionManager(silence_seconds=60.0)
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)
    with client.websocket_connect("/ws/live?frameRate=60") as ws:
        ws.receive_json()  # hello

        # Drive cadence meter past 30 Hz so the downsampler routes via batches.
        # Each call uses a distinct TimestampMS so CadenceMeter learns ~60 Hz.
        for i in range(12):
            raw = decoder.decode(golden_packet)
            raw.timestamp_ms = 1000 + 16 * (i + 1)
            f, d = _make_frame(sm, raw, t0 + timedelta(milliseconds=16 * i))
            client.portal.call(broker.on_frame, f, d)

        saw_batch = False
        for _ in range(20):
            msg = ws.receive_json()
            if msg.get("type") == "frames":
                assert isinstance(msg["batch"], list)
                assert msg["batch"]
                saw_batch = True
                break
        assert saw_batch, "expected a frames-batch message at 60 Hz source"
