"""Constitution Principle X (1): golden-byte decoder fixtures.

Covers: every field type round-trips, trailing-byte preservation,
malformed lengths rejected, WheelInPuddle = 0/1 bool, lap-time 0.0 → None
but LapNumber=0 legitimate.
"""

from __future__ import annotations

import pytest

from fh6.domain.ports.packet_decoder import MalformedPacket
from fh6.infrastructure.telemetry.fh6_decoder import FH6PacketDecoder


def test_packet_size_exactly_324(golden_packet: bytes) -> None:
    assert len(golden_packet) == 324
    assert FH6PacketDecoder.expected_packet_size == 324


def test_decode_round_trip(golden_packet: bytes) -> None:
    raw = FH6PacketDecoder().decode(golden_packet)
    assert raw.is_race_on is True
    assert raw.timestamp_ms == 1_000
    assert raw.engine["rpm"] == pytest.approx(6240.0, rel=1e-6)
    assert raw.engine["maxRpm"] == pytest.approx(8000.0, rel=1e-6)
    assert raw.race["lap"] == 8
    assert raw.race["position"] == 3
    assert raw.world["carOrdinal"] == 2451
    assert raw.world["carClass"] == "A"
    assert raw.drivetrain["type"] == "AWD"
    assert raw.tail_reserved_byte == 0


def test_inputs_normalized(golden_packet: bytes) -> None:
    raw = FH6PacketDecoder().decode(golden_packet)
    # accel = 214 → 214/255 ≈ 0.8392
    assert 0.83 < raw.inputs["throttle"] < 0.85
    assert raw.inputs["brake"] == 0.0
    # steer = -12 → -12/127 ≈ -0.0945
    assert -0.1 < raw.inputs["steer"] < -0.08


def test_wheel_in_puddle_is_boolean(make_packet) -> None:
    """FR-023: FH6 WheelInPuddle is S32 0/1, not a depth float."""
    payload = make_packet(InPuddleRL=1, InPuddleRR=0)
    raw = FH6PacketDecoder().decode(payload)
    assert raw.wheels["rl"]["inPuddle"] in (0, 1)
    assert raw.wheels["rr"]["inPuddle"] in (0, 1)
    assert raw.wheels["rl"]["inPuddle"] == 1
    assert raw.wheels["rr"]["inPuddle"] == 0


def test_lap_times_zero_becomes_none(make_packet) -> None:
    """FR-021 / API spec §12 item 9: 0.0 in lap-time fields → null."""
    payload = make_packet(BestLap=0.0, LastLap=0.0, CurrentLap=0.0)
    raw = FH6PacketDecoder().decode(payload)
    assert raw.race["bestLapS"] is None
    assert raw.race["lastLapS"] is None
    assert raw.race["currentLapS"] is None


def test_lap_number_zero_is_legitimate(make_packet) -> None:
    """FR-021 / API spec §12 item 10: LapNumber=0 is a real integer value,
    not "missing data". Distinct from the 0.0-lap-time convention above."""
    payload = make_packet(LapNumber=0)
    raw = FH6PacketDecoder().decode(payload)
    assert raw.race["lap"] == 0  # not None


def test_trailing_byte_preserved(make_packet) -> None:
    """FR-002 / API spec §12 item 1: byte 323 is preserved as
    tail_reserved_byte even though the documented fields end at offset 322."""
    payload = make_packet(TailReserved=0xA5)
    raw = FH6PacketDecoder().decode(payload)
    assert raw.tail_reserved_byte == 0xA5


def test_malformed_length_short(golden_packet: bytes) -> None:
    truncated = golden_packet[:-1]
    with pytest.raises(MalformedPacket):
        FH6PacketDecoder().decode(truncated)


def test_malformed_empty() -> None:
    with pytest.raises(MalformedPacket):
        FH6PacketDecoder().decode(b"")


def test_base_324_packet_decodes(golden_packet: bytes) -> None:
    """324-byte FH6 packets (no trailing tire wear) decode cleanly and
    report tire_wear_source='modeled'."""
    assert len(golden_packet) == 324
    raw = FH6PacketDecoder().decode(golden_packet)
    assert raw.tire_wear is None
    assert raw.tire_wear_source == "modeled"


def test_340_byte_packet_exposes_tire_wear(golden_packet: bytes) -> None:
    """Motorsport-style packets append 4 × f32 tire wear at offsets
    324..339. The decoder should surface those values on FrameRaw and
    flag the source as 'packet'."""
    import struct as _struct

    wear_bytes = _struct.pack("<ffff", 0.10, 0.15, 0.20, 0.25)
    payload = golden_packet + wear_bytes
    assert len(payload) == 340
    raw = FH6PacketDecoder().decode(payload)
    assert raw.tire_wear_source == "packet"
    assert raw.tire_wear is not None
    assert raw.tire_wear["fl"] == pytest.approx(0.10, rel=1e-6)
    assert raw.tire_wear["fr"] == pytest.approx(0.15, rel=1e-6)
    assert raw.tire_wear["rl"] == pytest.approx(0.20, rel=1e-6)
    assert raw.tire_wear["rr"] == pytest.approx(0.25, rel=1e-6)


def test_tire_temp_fahrenheit_to_celsius(make_packet) -> None:
    """Forza emits tire temps in Fahrenheit; decoder must convert to
    Celsius. 212°F → 100°C."""
    payload = make_packet(TireTempFL=212.0, TireTempFR=212.0, TireTempRL=212.0, TireTempRR=212.0)
    raw = FH6PacketDecoder().decode(payload)
    for wn in ("fl", "fr", "rl", "rr"):
        assert raw.wheels[wn]["tireTemp_c"] == pytest.approx(100.0, abs=1e-4)


def test_decoder_emits_tire_temp_norm_window(golden_packet: bytes) -> None:
    """Each wheel dict carries tireTemp_normWindow in [0, 1], computed
    from tireTemp_c via the fixed 70–115°C optimal window. Unblocks the
    tire_heatmap / tire_viz / tire_wear widgets which read this field."""
    raw = FH6PacketDecoder().decode(golden_packet)
    for corner in ("fl", "fr", "rl", "rr"):
        wheel = raw.wheels[corner]
        assert "tireTemp_normWindow" in wheel, f"missing tireTemp_normWindow on {corner}"
        norm = wheel["tireTemp_normWindow"]
        assert 0.0 <= norm <= 1.0
        # Sanity-check the math: (c - 70) / 45, clamped to [0, 1].
        c = wheel["tireTemp_c"]
        expected = max(0.0, min(1.0, (c - 70.0) / 45.0))
        assert norm == pytest.approx(expected, abs=1e-6)


def test_tire_temp_norm_window_clamps(make_packet) -> None:
    """Below the window → 0.0; above → 1.0. (Window is 70–115°C.)"""
    # 32°F == 0°C → well below low edge → 0.0
    cold = FH6PacketDecoder().decode(
        make_packet(TireTempFL=32.0, TireTempFR=32.0, TireTempRL=32.0, TireTempRR=32.0)
    )
    for wn in ("fl", "fr", "rl", "rr"):
        assert cold.wheels[wn]["tireTemp_normWindow"] == 0.0
    # 482°F == 250°C → well above high edge → 1.0
    hot = FH6PacketDecoder().decode(
        make_packet(TireTempFL=482.0, TireTempFR=482.0, TireTempRL=482.0, TireTempRR=482.0)
    )
    for wn in ("fl", "fr", "rl", "rr"):
        assert hot.wheels[wn]["tireTemp_normWindow"] == 1.0


def test_position_is_world_space(golden_packet: bytes) -> None:
    raw = FH6PacketDecoder().decode(golden_packet)
    assert raw.motion["position"]["x"] == pytest.approx(12843.6, rel=1e-4)
    assert raw.motion["position"]["y"] == pytest.approx(312.4, rel=1e-4)
    assert raw.motion["position"]["z"] == pytest.approx(-5421.9, rel=1e-4)
