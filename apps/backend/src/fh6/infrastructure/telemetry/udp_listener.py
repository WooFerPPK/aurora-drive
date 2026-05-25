from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from fh6.domain.entities.frame import FrameRaw
from fh6.domain.ports.packet_decoder import MalformedPacket, PacketDecoder
from fh6.infrastructure.logging import get_logger

log = get_logger(__name__)


FrameHandler = Callable[[FrameRaw, datetime], Awaitable[None]]


@dataclass(slots=True)
class TelemetryHealth:
    """Observable status of the UDP listener.

    Mutated by the listener (bind outcome) and the datagram protocol
    (last_packet_at). Read by the /health/telemetry router and the
    /ws/live one-shot bind-failed broadcast.
    """

    host: str
    port: int
    listening: bool = False
    bind_error: str | None = None
    last_packet_at: datetime | None = None


class _UDPProtocol(asyncio.DatagramProtocol):
    def __init__(
        self,
        decoder: PacketDecoder,
        queue: asyncio.Queue[tuple[FrameRaw, datetime]],
        stats: ListenerStats,
        health: TelemetryHealth | None = None,
    ) -> None:
        self._decoder = decoder
        self._queue = queue
        self._stats = stats
        self._health = health

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self._stats.packets_received += 1
        if self._health is not None:
            self._health.last_packet_at = datetime.now(UTC)
        try:
            frame = self._decoder.decode(data)
        except MalformedPacket as exc:
            self._stats.malformed += 1
            log.warning("malformed_packet", reason=str(exc), bytes=len(data))
            return
        # Forza emits packets with CarOrdinal=0 while in menus/loading
        # screens before any car is loaded. They have no real car to
        # attribute frames to and would violate the frames→cars FK on
        # insert, so drop them here at the boundary.
        if frame.world.get("carOrdinal", 0) == 0:
            self._stats.dropped_no_car += 1
            return
        try:
            self._queue.put_nowait((frame, datetime.now(UTC)))
        except asyncio.QueueFull:  # pragma: no cover — queue is unbounded by default
            self._stats.dropped_enqueue += 1
            log.error("ingest_queue_full")


class ListenerStats:
    __slots__ = ("dropped_enqueue", "dropped_no_car", "malformed", "packets_received")

    def __init__(self) -> None:
        self.packets_received = 0
        self.malformed = 0
        self.dropped_enqueue = 0
        self.dropped_no_car = 0


class UDPTelemetryListener:
    """Asyncio UDP listener bound to (host, port). Decodes synchronously
    and enqueues onto an asyncio.Queue; a separate consumer drains.

    Refuses to start if port falls in FH6's reserved [5200, 5300]
    range (FR-005, SC-010).
    """

    FORBIDDEN_PORT_LOW = 5200
    FORBIDDEN_PORT_HIGH = 5300

    def __init__(
        self,
        host: str,
        port: int,
        decoder: PacketDecoder,
        queue: asyncio.Queue[tuple[FrameRaw, datetime]],
    ) -> None:
        if self.FORBIDDEN_PORT_LOW <= port <= self.FORBIDDEN_PORT_HIGH:
            raise ValueError(
                f"listen port {port} is in FH6 reserved range "
                f"[{self.FORBIDDEN_PORT_LOW}, {self.FORBIDDEN_PORT_HIGH}]"
            )
        self._host = host
        self._port = port
        self._decoder = decoder
        self._queue = queue
        self._transport: asyncio.DatagramTransport | None = None
        self.stats = ListenerStats()
        self.health = TelemetryHealth(host=host, port=port)

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _UDPProtocol(self._decoder, self._queue, self.stats, self.health),
                local_addr=(self._host, self._port),
            )
        except OSError as exc:
            self.health.listening = False
            self.health.bind_error = str(exc)
            log.error(
                "udp_listener_bind_failed",
                host=self._host,
                port=self._port,
                error=str(exc),
                errno=exc.errno,
            )
            return
        self._transport = transport
        self.health.listening = True
        self.health.bind_error = None
        log.info("udp_listener_started", host=self._host, port=self._port)

    async def stop(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None
            self.health.listening = False
            log.info("udp_listener_stopped")
