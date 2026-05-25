"""Contract test: `/health/telemetry` reflects UDP bind failure.

When the listener's bind raises OSError (e.g. port already in use),
app startup must not crash; the health endpoint must report
`listening: false` with a populated `bind_error`.
"""

from __future__ import annotations

import asyncio
import socket
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fh6.infrastructure.telemetry.fh6_decoder import FH6PacketDecoder
from fh6.infrastructure.telemetry.udp_listener import UDPTelemetryListener
from fh6.interfaces.rest.health_router import router as health_router


@pytest.fixture
def occupied_port() -> Iterator[int]:
    """Bind a UDP socket to a free port and hold it for the test."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    try:
        yield port
    finally:
        sock.close()


def test_health_telemetry_reports_bind_failure(occupied_port: int) -> None:
    queue: asyncio.Queue = asyncio.Queue()
    listener = UDPTelemetryListener(
        host="127.0.0.1",
        port=occupied_port,
        decoder=FH6PacketDecoder(),
        queue=queue,
    )

    # Start the listener; OSError on bind must be swallowed.
    asyncio.run(listener.start())

    app = FastAPI()
    app.state.telemetry_health = listener.health
    app.state.container = app.state
    app.include_router(health_router, prefix="/health")

    with TestClient(app) as client:
        resp = client.get("/health/telemetry")

    assert resp.status_code == 200
    body = resp.json()
    assert body["listening"] is False
    assert body["host"] == "127.0.0.1"
    assert body["port"] == occupied_port
    assert body["bind_error"] is not None
    assert body["bind_error"] != ""
    assert body["last_packet_at"] is None
