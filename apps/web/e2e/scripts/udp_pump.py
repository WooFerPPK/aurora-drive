#!/usr/bin/env python3
"""Pump synthetic Forza Horizon "Data Out" UDP packets at 30 Hz.

Used by the Playwright e2e suite to drive `/ws/live` so the
"live frame visible" smoke can assert that the dashboard's
StatusPill reaches DRIVING. Reuses the backend's existing
golden-packet builder so the wire format stays in lockstep with
the decoder.

Stops on SIGTERM/SIGINT. Logs a packet count every second.
"""
from __future__ import annotations

import os
import signal
import socket
import sys
import time
from pathlib import Path

# Locate the backend so we can borrow `_pack_golden_packet` from
# its test fixtures. The function is plain Python — importing the
# conftest module has no side effects beyond registering pytest
# fixtures, which are inert when pytest itself isn't driving.
HERE = Path(__file__).resolve()
BACKEND = HERE.parents[4] / "apps" / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "src"))

from tests.conftest import _pack_golden_packet  # noqa: E402

HOST = os.environ.get("FH6_UDP_HOST", "127.0.0.1")
PORT = int(os.environ.get("FH6_UDP_PORT", "5302"))
HZ = float(os.environ.get("FH6_UDP_HZ", "30"))

_stop = False


def _handle_stop(signum: int, _frame: object) -> None:
    global _stop
    _stop = True


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    period = 1.0 / HZ
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    addr = (HOST, PORT)

    print(f"[udp_pump] -> {HOST}:{PORT} @ {HZ:.1f} Hz", flush=True)
    sent = 0
    last_report = time.monotonic()
    ts_ms = 0
    while not _stop:
        ts_ms = (ts_ms + int(round(period * 1000))) % (1 << 32)
        sock.sendto(_pack_golden_packet(TimestampMS=ts_ms), addr)
        sent += 1
        now = time.monotonic()
        if now - last_report >= 1.0:
            print(f"[udp_pump] sent={sent}", flush=True)
            last_report = now
        time.sleep(period)

    sock.close()
    print(f"[udp_pump] stopped after sent={sent}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
