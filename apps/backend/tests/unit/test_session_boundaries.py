"""Constitution Principle X (2): session boundary truth tables.

Covers: car-change split, silence split, sub-threshold silence does NOT
split, stream-paused emission is independent of session split.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fh6.application.services.session_manager import BoundaryEvent, SessionManager
from fh6.infrastructure.telemetry.fh6_decoder import FH6PacketDecoder


def _decode(payload: bytes):
    return FH6PacketDecoder().decode(payload)


def test_first_frame_opens_session(golden_packet: bytes) -> None:
    sm = SessionManager(silence_seconds=60.0)
    raw = _decode(golden_packet)
    at = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)
    d = sm.on_frame(raw, at)
    assert d.event == BoundaryEvent.SESSION_STARTED
    assert d.opened_session is not None
    assert d.closed_session is None
    assert sm.current is not None


def test_appended_within_threshold(golden_packet: bytes) -> None:
    sm = SessionManager(silence_seconds=60.0)
    raw = _decode(golden_packet)
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)
    sm.on_frame(raw, t0)
    d = sm.on_frame(raw, t0 + timedelta(seconds=30))
    assert d.event == BoundaryEvent.APPENDED
    assert d.closed_session is None


def test_silence_split(golden_packet: bytes) -> None:
    sm = SessionManager(silence_seconds=60.0)
    raw = _decode(golden_packet)
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)
    first = sm.on_frame(raw, t0).opened_session
    d = sm.on_frame(raw, t0 + timedelta(seconds=120))
    assert d.event == BoundaryEvent.SESSION_STARTED
    assert d.closed_session is not None
    assert d.closed_session.id == first.id
    assert d.opened_session is not None
    assert d.opened_session.id != first.id
    assert d.closed_session.closed_reason.value == "silence"


def test_silence_threshold_boundary_does_not_split(golden_packet: bytes, make_packet) -> None:
    sm = SessionManager(silence_seconds=60.0)
    raw = _decode(golden_packet)
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)
    sm.on_frame(raw, t0)
    # Exactly at the threshold → does NOT split (strict `>`).
    d = sm.on_frame(raw, t0 + timedelta(seconds=60))
    assert d.event == BoundaryEvent.APPENDED


def test_car_change_split(make_packet) -> None:
    sm = SessionManager(silence_seconds=60.0)
    car_a = FH6PacketDecoder().decode(make_packet(CarOrdinal=2451, CarPI=812))
    car_b = FH6PacketDecoder().decode(make_packet(CarOrdinal=9999, CarPI=820))
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)
    first = sm.on_frame(car_a, t0).opened_session
    d = sm.on_frame(car_b, t0 + timedelta(seconds=5))  # well under silence
    assert d.event == BoundaryEvent.SESSION_STARTED
    assert d.closed_session is not None
    assert d.closed_session.id == first.id
    assert d.closed_session.closed_reason.value == "car_change"
    assert d.opened_session is not None
    assert d.opened_session.car_id != first.car_id


def test_consecutive_appends_update_last_frame_at(golden_packet: bytes) -> None:
    sm = SessionManager(silence_seconds=60.0)
    raw = _decode(golden_packet)
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)
    sm.on_frame(raw, t0)
    sm.on_frame(raw, t0 + timedelta(seconds=10))
    sm.on_frame(raw, t0 + timedelta(seconds=20))
    assert sm.last_frame_at == t0 + timedelta(seconds=20)
