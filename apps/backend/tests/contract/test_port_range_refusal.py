"""FR-005 + SC-010: refuse to start when listen port falls in
FH6's reserved [5200, 5300] range. Accept any other port.
"""

from __future__ import annotations

import asyncio

import pytest

from fh6.infrastructure.telemetry.fh6_decoder import FH6PacketDecoder
from fh6.infrastructure.telemetry.udp_listener import UDPTelemetryListener


@pytest.mark.parametrize("port", [5200, 5210, 5250, 5290, 5300])
def test_refuses_forbidden_ports(port: int) -> None:
    queue: asyncio.Queue = asyncio.Queue()
    with pytest.raises(ValueError, match="reserved range"):
        UDPTelemetryListener(host="127.0.0.1", port=port, decoder=FH6PacketDecoder(), queue=queue)


@pytest.mark.parametrize("port", [1024, 5199, 5301, 5302, 8000, 65535])
def test_accepts_allowed_ports_at_construct_time(port: int) -> None:
    queue: asyncio.Queue = asyncio.Queue()
    listener = UDPTelemetryListener(
        host="127.0.0.1", port=port, decoder=FH6PacketDecoder(), queue=queue
    )
    assert listener is not None
