"""Constitution Principle X (3): physics derivations analytic cases.

Each derived field has a hand-computed expected value from controlled
raw input. If a derivation drifts from its analytic answer the test
fails immediately.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fh6.application.services import derivations
from fh6.domain.entities.frame import DecodedFrame, FrameDerived, FrameModeled
from fh6.domain.value_objects.confidence import Confidence
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.infrastructure.telemetry.fh6_decoder import FH6PacketDecoder


def _decode(payload: bytes):
    return FH6PacketDecoder().decode(payload)


def _frame_from(raw, at: datetime, throttle_norm: float | None = None) -> DecodedFrame:
    if throttle_norm is not None:
        raw.inputs["throttle"] = throttle_norm
    return DecodedFrame(
        session_id=SessionId("s_test"),
        car_id=CarId("car_test"),
        received_at=at,
        raw=raw,
        derived=FrameDerived(),
        modeled=FrameModeled(
            tire_wear={"fl": 0.0, "fr": 0.0, "rl": 0.0, "rr": 0.0},
            tire_wear_confidence=Confidence(
                value=0.0, tolerance_band=0.0, model_version="placeholder"
            ),
        ),
    )


def test_balance_neutral(golden_packet: bytes) -> None:
    raw = _decode(golden_packet)
    assert derivations.balance(raw) == 0.0


def test_balance_oversteer(make_packet) -> None:
    raw = _decode(make_packet(CombSlipFL=0.05, CombSlipFR=0.05, CombSlipRL=0.15, CombSlipRR=0.15))
    # front=0.05, rear=0.15, (rear-front)/(rear+front) = 0.5
    assert abs(derivations.balance(raw) - 0.5) < 1e-6


def test_balance_understeer(make_packet) -> None:
    raw = _decode(make_packet(CombSlipFL=0.20, CombSlipFR=0.20, CombSlipRL=0.05, CombSlipRR=0.05))
    assert derivations.balance(raw) == -0.6


def test_weight_front_50_50(golden_packet: bytes) -> None:
    raw = _decode(golden_packet)
    # All suspNorm=0.5 → fraction = 0.5
    assert derivations.weight_front(raw) == 0.5


def test_weight_front_loaded(make_packet) -> None:
    raw = _decode(make_packet(SuspNormFL=0.8, SuspNormFR=0.8, SuspNormRL=0.2, SuspNormRR=0.2))
    # front=1.6, rear=0.4, total=2.0 → 0.8
    assert abs(derivations.weight_front(raw) - 0.8) < 1e-6


def test_weight_left(make_packet) -> None:
    raw = _decode(make_packet(SuspNormFL=0.6, SuspNormFR=0.4, SuspNormRL=0.6, SuspNormRR=0.4))
    # left=1.2, total=2.0 → 0.6
    assert abs(derivations.weight_left(raw) - 0.6) < 1e-6


def test_grip_budget_used(make_packet) -> None:
    raw = _decode(make_packet(CombSlipFL=0.1, CombSlipFR=0.2, CombSlipRL=0.3, CombSlipRR=0.4))
    # mean = 0.25
    assert abs(derivations.grip_budget_used(raw) - 0.25) < 1e-6


def test_grip_budget_clamped(make_packet) -> None:
    raw = _decode(make_packet(CombSlipFL=2.0, CombSlipFR=2.0, CombSlipRL=2.0, CombSlipRR=2.0))
    assert derivations.grip_budget_used(raw) == 1.0


def test_power_band_occupancy_below_band(make_packet) -> None:
    raw = _decode(make_packet(EngineIdleRpm=1000.0, EngineMaxRpm=9000.0, CurrentEngineRpm=4000.0))
    # band low = 5000; rpm=4000 → 0
    assert derivations.power_band_occupancy(raw) == 0.0


def test_power_band_occupancy_in_band(make_packet) -> None:
    raw = _decode(make_packet(EngineIdleRpm=1000.0, EngineMaxRpm=9000.0, CurrentEngineRpm=7000.0))
    # band low=5000, range=4000, rpm-low=2000 → 0.5
    assert abs(derivations.power_band_occupancy(raw) - 0.5) < 1e-6


def test_power_band_occupancy_redline(make_packet) -> None:
    raw = _decode(make_packet(EngineIdleRpm=1000.0, EngineMaxRpm=9000.0, CurrentEngineRpm=9000.0))
    assert derivations.power_band_occupancy(raw) == 1.0


def test_throttle_smoothness_constant(golden_packet: bytes) -> None:
    raw = _decode(golden_packet)
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)
    window = [
        _frame_from(_decode(golden_packet), t0 + timedelta(milliseconds=33 * i)) for i in range(8)
    ]
    # All identical throttle → stdev=0 → 1.0
    assert derivations.throttle_smoothness(window) == 1.0


def test_throttle_smoothness_oscillating(golden_packet: bytes) -> None:
    raw = _decode(golden_packet)
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)
    frames: list[DecodedFrame] = []
    # 50/50 mix of throttle=0 / throttle=1 → stdev=0.5 → smoothness=0
    for i in range(8):
        thr = 0.0 if i % 2 == 0 else 1.0
        f = _frame_from(
            _decode(golden_packet), t0 + timedelta(milliseconds=33 * i), throttle_norm=thr
        )
        frames.append(f)
    smoothness = derivations.throttle_smoothness(frames)
    assert smoothness == 0.0


def test_body_control_stable(golden_packet: bytes) -> None:
    t0 = datetime(2026, 5, 17, 12, 0, 0, tzinfo=UTC)
    frames = [
        _frame_from(_decode(golden_packet), t0 + timedelta(milliseconds=33 * i)) for i in range(6)
    ]
    assert derivations.body_control(frames) == 1.0


def test_compute_bundles_all_fields(golden_packet: bytes) -> None:
    raw = _decode(golden_packet)
    d = derivations.compute(raw, [])
    # All inputs balanced → all fields at neutral / 1.0.
    assert d.balance == 0.0
    assert d.weight_front == 0.5
    assert d.weight_left == 0.5
    assert d.body_control == 1.0
    assert d.power_band_occupancy > 0.0  # 6240 RPM is above band-low for idle=900/max=8000
    assert 0.0 <= d.grip_budget_used <= 1.0
    assert d.throttle_smoothness == 1.0
    # Golden packet has +Z velocity with +Z acceleration — accelerating, not
    # decelerating, so stop_distance projects to 0 (the gate).
    assert d.stop_distance_m == 0.0


def test_stop_distance_braking_along_motion(make_packet) -> None:
    # Heading +Z at 40 m/s, decelerating at 8 m/s² (acceleration vector
    # opposed to velocity). Expected: 40² / (2·8) = 100 m.
    raw = _decode(
        make_packet(
            Speed=40.0,
            VelX=0.0,
            VelY=0.0,
            VelZ=40.0,
            AccelX=0.0,
            AccelY=0.0,
            AccelZ=-8.0,
        )
    )
    assert abs(derivations.stop_distance(raw) - 100.0) < 1e-6


def test_stop_distance_coasting_returns_zero(make_packet) -> None:
    # 40 m/s, no longitudinal accel — not actually decelerating.
    raw = _decode(
        make_packet(
            Speed=40.0,
            VelX=0.0,
            VelY=0.0,
            VelZ=40.0,
            AccelX=0.0,
            AccelY=0.0,
            AccelZ=0.0,
        )
    )
    assert derivations.stop_distance(raw) == 0.0


def test_stop_distance_pure_lateral_accel_returns_zero(make_packet) -> None:
    # Cornering hard at constant speed: acceleration is perpendicular to
    # velocity, so projection onto -v̂ is 0 → no braking projected.
    raw = _decode(
        make_packet(
            Speed=40.0,
            VelX=0.0,
            VelY=0.0,
            VelZ=40.0,
            AccelX=10.0,
            AccelY=0.0,
            AccelZ=0.0,
        )
    )
    assert derivations.stop_distance(raw) == 0.0


def test_stop_distance_near_stationary_returns_zero(make_packet) -> None:
    raw = _decode(
        make_packet(
            Speed=0.5,
            VelX=0.0,
            VelY=0.0,
            VelZ=0.5,
            AccelX=0.0,
            AccelY=0.0,
            AccelZ=-8.0,
        )
    )
    assert derivations.stop_distance(raw) == 0.0


def test_stop_distance_reverse_braking(make_packet) -> None:
    # Reversing (−Z velocity) with +Z acceleration — that's deceleration
    # along motion. 20² / (2·4) = 50 m.
    raw = _decode(
        make_packet(
            Speed=20.0,
            VelX=0.0,
            VelY=0.0,
            VelZ=-20.0,
            AccelX=0.0,
            AccelY=0.0,
            AccelZ=4.0,
        )
    )
    assert abs(derivations.stop_distance(raw) - 50.0) < 1e-6
