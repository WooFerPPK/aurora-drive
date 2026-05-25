from __future__ import annotations

from typing import Protocol

from fh6.domain.entities.frame import FrameRaw


class PacketDecoder(Protocol):
    """Decodes a 324-byte FH6 Data Out datagram into FrameRaw.
    Raises MalformedPacket on bad length or content."""

    expected_packet_size: int

    def decode(self, payload: bytes) -> FrameRaw: ...


class MalformedPacket(ValueError):
    """Raised when a datagram cannot be decoded. Caller increments
    a malformed-packet counter and continues (FR-002)."""
