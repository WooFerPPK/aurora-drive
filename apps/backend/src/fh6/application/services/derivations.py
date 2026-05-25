"""Physics derivations (T057, constitution Principle X (3)).

Pure functions over `FrameRaw` and the trailing 3 s window from
`HotCache`. Every field has an analytic answer reachable by hand from
the inputs — `tests/unit/test_derivations_analytic.py` pins each.

API spec §2 documents the field shapes. Values are normalized to
[-1, 1] or [0, 1] as noted per field.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from fh6.domain.entities.frame import DecodedFrame, FrameDerived, FrameRaw


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _signed_clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _susp_norm(raw: FrameRaw, key: str) -> float:
    return float(raw.wheels[key]["suspensionTravel_norm"])


def _slip(raw: FrameRaw, key: str) -> float:
    return float(raw.wheels[key]["combinedSlip"])


def balance(raw: FrameRaw) -> float:
    """Front/rear grip balance.

    +1 = total rear oversteer (rear sliding more); -1 = total understeer
    (front sliding more); 0 = neutral. Computed from combined-slip
    front/rear average.
    """
    front = (_slip(raw, "fl") + _slip(raw, "fr")) * 0.5
    rear = (_slip(raw, "rl") + _slip(raw, "rr")) * 0.5
    denom = front + rear
    if denom <= 0:
        return 0.0
    return _signed_clamp((rear - front) / denom)


def weight_front(raw: FrameRaw) -> float:
    """Fraction of vertical load on front axle, derived from compressed
    suspension travel. 0 = no front load, 1 = all on front. Default 0.5.
    """
    fl = _susp_norm(raw, "fl")
    fr = _susp_norm(raw, "fr")
    rl = _susp_norm(raw, "rl")
    rr = _susp_norm(raw, "rr")
    total = fl + fr + rl + rr
    if total <= 0:
        return 0.5
    return _clamp((fl + fr) / total)


def weight_left(raw: FrameRaw) -> float:
    """Fraction of vertical load on left side. 0.5 = even."""
    fl = _susp_norm(raw, "fl")
    fr = _susp_norm(raw, "fr")
    rl = _susp_norm(raw, "rl")
    rr = _susp_norm(raw, "rr")
    total = fl + fr + rl + rr
    if total <= 0:
        return 0.5
    return _clamp((fl + rl) / total)


def grip_budget_used(raw: FrameRaw) -> float:
    """Mean combined-slip across all four wheels, clamped to [0, 1].

    Combined-slip is a friction-circle saturation metric in FH telemetry —
    treating its mean as a unit-less grip-budget proxy is a deliberate
    simplification (research notes accept this for v0).
    """
    s = (_slip(raw, "fl") + _slip(raw, "fr") + _slip(raw, "rl") + _slip(raw, "rr")) / 4.0
    return _clamp(s)


def power_band_occupancy(raw: FrameRaw) -> float:
    """How close engine RPM is to the documented power band.

    Power band proxied as [idle + 0.5*(max-idle), max] — the upper half of
    the operational range. Returns the fraction of that interval the
    current RPM occupies, clamped [0, 1]. Below the band → 0.
    """
    rpm = float(raw.engine["rpm"])
    idle = float(raw.engine["idleRpm"])
    rpm_max = float(raw.engine["maxRpm"])
    if rpm_max <= idle:
        return 0.0
    band_low = idle + 0.5 * (rpm_max - idle)
    if rpm <= band_low:
        return 0.0
    return _clamp((rpm - band_low) / (rpm_max - band_low))


def throttle_smoothness(window: Sequence[DecodedFrame]) -> float:
    """1 minus normalized stdev of throttle inputs across the window.

    Constant throttle → 1.0. Wildly oscillating → near 0.
    Window of 0 or 1 frames → 1.0 (no oscillation observable).
    """
    if len(window) < 2:
        return 1.0
    samples = [float(f.raw.inputs["throttle"]) for f in window]
    mean = sum(samples) / len(samples)
    variance = sum((s - mean) ** 2 for s in samples) / len(samples)
    stdev = variance**0.5
    return _clamp(1.0 - 2.0 * stdev)


def stop_distance(raw: FrameRaw) -> float:
    """Kinematic stopping distance in meters at the current deceleration.

    Project the world-frame acceleration onto -velocity to get the true
    longitudinal deceleration (slip-aware: pure lateral acceleration in
    a corner doesn't read as braking). Then v² / (2·a).

    Returns 0 when:
    - speed is below 1 m/s (nothing meaningful to project), or
    - decel along motion is below 0.5 m/s² (coasting or accelerating —
      the projection isn't physical).

    Consumers (world_map widget's brake overlay, future brake-distance
    gauge) treat 0 as "hide the indicator."
    """
    speed = float(raw.motion["speed_mps"])
    if speed < 1.0:
        return 0.0
    vx = float(raw.motion["velocity"]["x"])
    vz = float(raw.motion["velocity"]["z"])
    ax = float(raw.motion["acceleration"]["x"])
    az = float(raw.motion["acceleration"]["z"])
    speed_planar = (vx * vx + vz * vz) ** 0.5
    if speed_planar < 1.0:
        return 0.0
    # Project acceleration vector onto -v̂. Positive = decelerating.
    decel = -(ax * vx + az * vz) / speed_planar
    if decel < 0.5:
        return 0.0
    return float((speed * speed) / (2.0 * decel))


def body_control(window: Sequence[DecodedFrame]) -> float:
    """1 minus normalized stdev of suspension load distribution.

    Stable platform → 1.0; high pitch/roll oscillation → low.
    """
    if len(window) < 2:
        return 1.0
    samples: list[float] = []
    for f in window:
        fl = float(f.raw.wheels["fl"]["suspensionTravel_norm"])
        fr = float(f.raw.wheels["fr"]["suspensionTravel_norm"])
        rl = float(f.raw.wheels["rl"]["suspensionTravel_norm"])
        rr = float(f.raw.wheels["rr"]["suspensionTravel_norm"])
        samples.append((fl + fr + rl + rr) / 4.0)
    mean = sum(samples) / len(samples)
    variance = sum((s - mean) ** 2 for s in samples) / len(samples)
    stdev = variance**0.5
    return _clamp(1.0 - 4.0 * stdev)


def compute(
    raw: FrameRaw,
    window: Sequence[DecodedFrame] = (),
) -> FrameDerived:
    """Bundle every per-frame derived field. `window` is the trailing
    3 s of DecodedFrames (HotCache) — required for the time-domain
    derivations (`throttle_smoothness`, `body_control`).
    """
    return FrameDerived(
        balance=balance(raw),
        weight_front=weight_front(raw),
        weight_left=weight_left(raw),
        body_control=body_control(window),
        grip_budget_used=grip_budget_used(raw),
        power_band_occupancy=power_band_occupancy(raw),
        throttle_smoothness=throttle_smoothness(window),
        stop_distance_m=stop_distance(raw),
    )


def apply(frame: DecodedFrame, window: Sequence[DecodedFrame] = ()) -> DecodedFrame:
    frame.derived = compute(frame.raw, window)
    return frame


WINDOW_LOOKBACK = timedelta(seconds=3)
