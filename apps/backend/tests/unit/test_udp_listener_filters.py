"""UDP listener boundary filtering.

Forza emits packets with CarOrdinal=0 while in menus / loading screens
before any car is loaded. They have no real car to attribute frames to
and would violate the frames→cars FK on insert, so the listener drops
them before they ever reach the ingest queue.
"""

from __future__ import annotations

import asyncio
from datetime import UTC

from fh6.infrastructure.telemetry.fh6_decoder import FH6PacketDecoder
from fh6.infrastructure.telemetry.udp_listener import (
    ListenerStats,
    _UDPProtocol,
)


def _protocol() -> tuple[_UDPProtocol, asyncio.Queue, ListenerStats]:
    queue: asyncio.Queue = asyncio.Queue()
    stats = ListenerStats()
    return _UDPProtocol(FH6PacketDecoder(), queue, stats), queue, stats


def test_drops_packet_with_car_ordinal_zero(make_packet) -> None:
    proto, queue, stats = _protocol()
    proto.datagram_received(make_packet(CarOrdinal=0), ("127.0.0.1", 5300))

    assert queue.empty()
    assert stats.packets_received == 1
    assert stats.dropped_no_car == 1
    assert stats.malformed == 0


def test_enqueues_packet_with_real_car_ordinal(make_packet) -> None:
    proto, queue, stats = _protocol()
    proto.datagram_received(make_packet(CarOrdinal=2451), ("127.0.0.1", 5300))

    assert queue.qsize() == 1
    assert stats.packets_received == 1
    assert stats.dropped_no_car == 0


def test_enqueued_timestamp_is_timezone_aware(make_packet) -> None:
    proto, queue, _ = _protocol()
    proto.datagram_received(make_packet(CarOrdinal=2451), ("127.0.0.1", 5300))

    _, ts = queue.get_nowait()
    assert ts.tzinfo is not None and ts.tzinfo.utcoffset(ts) is not None
    assert ts.tzinfo == UTC
