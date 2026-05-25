"""Unit tests for ChangePointDetector — TDD RED-GREEN cycle.

Tests verify: no-fire on stable signal, positive/negative drift firing,
single-bin no-fire, pause-after-fire, reset, fingerprint isolation,
missing stored_bin graceful handling, stride gating, and callback
exception swallowing.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime

from fh6.application.services.shift.change_point import ChangePointDetector, ChangePointEvent
from fh6.domain.ports.shift_predictor_repo import BinRecord
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint
from fh6.infrastructure.config import AppConfig

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 5, 23, 10, 0, 0, tzinfo=UTC)

_FP_A = EngineFingerprint(car_ordinal=2451, performance_index=812, num_cylinders=6)
_FP_B = EngineFingerprint(car_ordinal=9999, performance_index=700, num_cylinders=4)


def _cfg(
    z_threshold: float = 3.0,
    bins_required: int = 3,
) -> AppConfig:
    """Construct a minimal AppConfig with the shift change-point fields set."""
    return AppConfig(
        listen_addr="127.0.0.1",
        listen_port=5302,
        http_host="127.0.0.1",
        http_port=8000,
        db_dsn="postgresql+asyncpg://fh6:fh6@127.0.0.1:5432/fh6",
        llm_dry_run=False,
        log_level="INFO",
        log_format="pretty",
        rewind_continuity_threshold_m=20.0,
        rewind_match_tolerance_m=5.0,
        rewind_yaw_tolerance_rad=math.pi / 2,
        rewind_pause_floor_ms=250,
        shift_throttle_min=0.95,
        shift_brake_max=0.05,
        shift_steer_max=0.10,
        shift_combined_slip_max=0.20,
        shift_gear_stable_frames=5,
        shift_warmup_seconds=60,
        shift_boost_settle_psi_per_s=1.0,
        shift_ewma_half_life_samples=54000,
        shift_bin_min_count=10,
        shift_pair_learned_samples=200,
        shift_change_z_threshold=z_threshold,
        shift_change_bins_required=bins_required,
        shift_recompute_every_n=50,
        shift_display_throttle_min=0.70,
        shift_turbo_residual_delay_ms=500,
        shift_na_residual_delay_ms=300,
        shift_residual_window_ms=200,
        shift_prior_rebuild_cooldown_s=300,
        shift_prior_min_fp_samples=1000,
        shift_tcs_slip_threshold=0.50,
        shift_tcs_torque_floor_ratio=0.85,
        shift_assist_alert_pct=0.05,
        shift_assist_recent_window=900,
        shift_trans_mode_ring_cap=30,
        shift_trans_mode_min_samples=10,
        shift_trans_mode_auto_stdev_rpm=50.0,
        shift_downshift_brake_display_min=0.10,
        shift_downshift_throttle_display_max=0.30,
    )


class CallbackRecorder:
    """Deterministic sink for ChangePointEvent callbacks."""

    def __init__(self) -> None:
        self.events: list[ChangePointEvent] = []

    def __call__(self, event: ChangePointEvent) -> None:
        self.events.append(event)


def _make_stored_bin(
    fp: EngineFingerprint,
    rpm_bin: int,
    mean: float,
    std: float,
    count: int = 200,
    gear: int = 3,
) -> BinRecord:
    """Fabricate a BinRecord with a known mean and variance (std²·count)."""
    variance = std**2
    m2 = variance * max(1, count - 1)
    return BinRecord(
        fingerprint=fp,
        gear=gear,
        rpm_bin=rpm_bin,
        count=count,
        mean_torque_nm=mean,
        m2_torque=m2,
        q90_torque_nm=mean + 1.28 * std,
        mean_boost_psi=8.0,
        last_updated=_NOW,
    )


def _observe_many(
    detector: ChangePointDetector,
    fp: EngineFingerprint,
    rpm_values: list[float],
    torque_values: list[float],
    stored_bin_fn,
    gear: int = 3,
    at: datetime = _NOW,
) -> None:
    """Feed (rpm, torque) pairs into the detector, computing stored_bin per sample."""
    assert len(rpm_values) == len(torque_values)
    for rpm, torque in zip(rpm_values, torque_values):
        rpm_bin = int(rpm / 100)
        stored = stored_bin_fn(rpm_bin)
        detector.observe(fp, gear, rpm, torque, at, stored)


# ---------------------------------------------------------------------------
# Test 1: No drift → no fire
# ---------------------------------------------------------------------------


def test_no_drift_no_fire() -> None:
    """100 samples drawn from N(mean=400, std=20) across 5 bins should NOT fire."""
    rng = random.Random(42)
    cfg = _cfg()
    recorder = CallbackRecorder()
    detector = ChangePointDetector(config=cfg, on_change_point=recorder)

    # 5 contiguous bins: rpm 6000–6400 (bins 60–64)
    bins_rpm = [6000.0, 6100.0, 6200.0, 6300.0, 6400.0]
    stored_mean = 400.0
    stored_std = 20.0

    # 20 samples per bin = 100 total; samples drawn near stored mean
    for rpm in bins_rpm:
        rpm_bin = int(rpm / 100)
        stored = _make_stored_bin(_FP_A, rpm_bin, stored_mean, stored_std)
        for _ in range(20):
            torque = rng.gauss(stored_mean, stored_std)
            detector.observe(_FP_A, 3, rpm, torque, _NOW, stored)

    assert len(recorder.events) == 0
    assert not detector.is_paused(_FP_A)


# ---------------------------------------------------------------------------
# Test 2: Positive drift fires
# ---------------------------------------------------------------------------


def test_positive_drift_fires() -> None:
    """Positive shift across ≥3 contiguous bins fires with direction='positive'.

    Strategy: feed all samples from the shifted distribution (no warmup phase)
    so window_mean is clearly above stored_mean. With stored_std=20 and
    shift=100, z = 100/20 = 5 >> z_threshold=3. We use 25 samples per bin
    (3 bins × 25 = 75 samples total, within WINDOW_SIZE=100).
    """
    rng = random.Random(7)
    cfg = _cfg(z_threshold=3.0, bins_required=3)
    recorder = CallbackRecorder()
    detector = ChangePointDetector(config=cfg, on_change_point=recorder)

    stored_mean = 400.0
    stored_std = 20.0
    shift = 100.0  # z = 5 >> 3

    # 3 contiguous bins: 60, 61, 62 (rpm 6000, 6100, 6200)
    drift_bins = [60, 61, 62]
    all_rpms: list[float] = []
    all_torques: list[float] = []
    stored_by_bin: dict[int, BinRecord] = {}

    for rpm_bin in drift_bins:
        rpm = float(rpm_bin * 100)
        stored = _make_stored_bin(_FP_A, rpm_bin, stored_mean, stored_std)
        stored_by_bin[rpm_bin] = stored
        # 25 samples all from shifted distribution (total 75 ≤ WINDOW_SIZE=100)
        for _ in range(25):
            all_rpms.append(rpm)
            all_torques.append(rng.gauss(stored_mean + shift, stored_std * 0.5))

    def stored_fn(rpm_bin: int) -> BinRecord | None:
        return stored_by_bin.get(rpm_bin)

    _observe_many(detector, _FP_A, all_rpms, all_torques, stored_fn)

    assert len(recorder.events) >= 1
    evt = recorder.events[0]
    assert evt.direction == "positive"
    assert evt.bins_affected >= 3
    assert evt.fingerprint == _FP_A


# ---------------------------------------------------------------------------
# Test 3: Negative drift fires
# ---------------------------------------------------------------------------


def test_negative_drift_fires() -> None:
    """Negative shift across ≥3 contiguous bins fires with direction='negative'.

    Same strategy as the positive test: all shifted, z = 100/20 = 5 >> 3.
    """
    rng = random.Random(13)
    cfg = _cfg(z_threshold=3.0, bins_required=3)
    recorder = CallbackRecorder()
    detector = ChangePointDetector(config=cfg, on_change_point=recorder)

    stored_mean = 400.0
    stored_std = 20.0
    shift = -100.0  # z = -5 << -3

    drift_bins = [60, 61, 62]
    all_rpms: list[float] = []
    all_torques: list[float] = []
    stored_by_bin: dict[int, BinRecord] = {}

    for rpm_bin in drift_bins:
        rpm = float(rpm_bin * 100)
        stored = _make_stored_bin(_FP_A, rpm_bin, stored_mean, stored_std)
        stored_by_bin[rpm_bin] = stored
        # 25 samples all from shifted distribution
        for _ in range(25):
            all_rpms.append(rpm)
            all_torques.append(rng.gauss(stored_mean + shift, stored_std * 0.5))

    def stored_fn(rpm_bin: int) -> BinRecord | None:
        return stored_by_bin.get(rpm_bin)

    _observe_many(detector, _FP_A, all_rpms, all_torques, stored_fn)

    assert len(recorder.events) >= 1
    evt = recorder.events[0]
    assert evt.direction == "negative"
    assert evt.bins_affected >= 3
    assert evt.fingerprint == _FP_A


# ---------------------------------------------------------------------------
# Test 4: Single deviating bin does not fire
# ---------------------------------------------------------------------------


def test_single_bin_deviation_does_not_fire() -> None:
    """Only 1 bin deviating (bins_required=3) should NOT fire."""
    rng = random.Random(99)
    cfg = _cfg(z_threshold=3.0, bins_required=3)
    recorder = CallbackRecorder()
    detector = ChangePointDetector(config=cfg, on_change_point=recorder)

    stored_mean = 400.0
    stored_std = 20.0
    shift = 200.0  # huge shift but only in ONE bin

    # Bin 60 deviates; bins 61, 62 are stable
    stable_bins = [61, 62, 63, 64]
    deviant_bin = 60

    stored_by_bin: dict[int, BinRecord] = {}
    all_rpms: list[float] = []
    all_torques: list[float] = []

    # Feed stable data for stable bins (≥5 samples each for MIN_BIN_SAMPLES)
    for rpm_bin in stable_bins:
        rpm = float(rpm_bin * 100)
        stored = _make_stored_bin(_FP_A, rpm_bin, stored_mean, stored_std)
        stored_by_bin[rpm_bin] = stored
        for _ in range(20):
            all_rpms.append(rpm)
            all_torques.append(rng.gauss(stored_mean, stored_std * 0.5))

    # Deviant bin with huge shift
    rpm = float(deviant_bin * 100)
    stored = _make_stored_bin(_FP_A, deviant_bin, stored_mean, stored_std)
    stored_by_bin[deviant_bin] = stored
    for _ in range(20):
        all_rpms.append(rpm)
        all_torques.append(rng.gauss(stored_mean + shift, stored_std * 0.1))

    def stored_fn(rpm_bin: int) -> BinRecord | None:
        return stored_by_bin.get(rpm_bin)

    _observe_many(detector, _FP_A, all_rpms, all_torques, stored_fn)

    assert len(recorder.events) == 0
    assert not detector.is_paused(_FP_A)


# ---------------------------------------------------------------------------
# Test 5: Pause after fire — subsequent observes don't fire again
# ---------------------------------------------------------------------------


def test_pause_after_fire_no_double_fire() -> None:
    """After first fire, is_paused(fp)==True and 100 more observes don't fire again."""
    rng = random.Random(7)
    cfg = _cfg(z_threshold=3.0, bins_required=3)
    recorder = CallbackRecorder()
    detector = ChangePointDetector(config=cfg, on_change_point=recorder)

    stored_mean = 400.0
    stored_std = 20.0
    shift = 100.0

    drift_bins = [60, 61, 62]
    stored_by_bin: dict[int, BinRecord] = {}

    # All samples from shifted distribution (25 per bin, 75 total ≤ WINDOW_SIZE)
    for rpm_bin in drift_bins:
        rpm = float(rpm_bin * 100)
        stored = _make_stored_bin(_FP_A, rpm_bin, stored_mean, stored_std)
        stored_by_bin[rpm_bin] = stored
        for _ in range(25):
            detector.observe(
                _FP_A, 3, rpm, rng.gauss(stored_mean + shift, stored_std * 0.5), _NOW, stored
            )

    # Must have fired at least once
    assert len(recorder.events) >= 1
    assert detector.is_paused(_FP_A)

    events_after_first_fire = len(recorder.events)

    # Feed 100 more deviating samples — should NOT fire again
    for _ in range(100):
        rpm_bin = 60
        rpm = float(rpm_bin * 100)
        stored = stored_by_bin[rpm_bin]
        detector.observe(
            _FP_A, 3, rpm, rng.gauss(stored_mean + shift, stored_std * 0.5), _NOW, stored
        )

    assert len(recorder.events) == events_after_first_fire


# ---------------------------------------------------------------------------
# Test 6: reset() unpauses and clears window
# ---------------------------------------------------------------------------


def test_reset_unpauses_and_clears_window() -> None:
    """After fire + reset(), fingerprint is no longer paused and fresh state accumulates."""
    rng = random.Random(7)
    cfg = _cfg(z_threshold=3.0, bins_required=3)
    recorder = CallbackRecorder()
    detector = ChangePointDetector(config=cfg, on_change_point=recorder)

    stored_mean = 400.0
    stored_std = 20.0
    shift = 100.0
    drift_bins = [60, 61, 62]
    stored_by_bin: dict[int, BinRecord] = {}

    # Cause a fire: all samples from shifted distribution
    for rpm_bin in drift_bins:
        rpm = float(rpm_bin * 100)
        stored = _make_stored_bin(_FP_A, rpm_bin, stored_mean, stored_std)
        stored_by_bin[rpm_bin] = stored
        for _ in range(25):
            detector.observe(
                _FP_A, 3, rpm, rng.gauss(stored_mean + shift, stored_std * 0.5), _NOW, stored
            )

    assert detector.is_paused(_FP_A)

    # Reset
    detector.reset(_FP_A)

    assert not detector.is_paused(_FP_A)

    # After reset, feed stable samples — should not crash and should accumulate fresh
    for rpm_bin in drift_bins:
        rpm = float(rpm_bin * 100)
        stored = stored_by_bin[rpm_bin]
        for _ in range(5):
            detector.observe(_FP_A, 3, rpm, rng.gauss(stored_mean, stored_std * 0.5), _NOW, stored)

    # Stable data shouldn't re-fire (under 3 sigma drift)
    assert not detector.is_paused(_FP_A)


# ---------------------------------------------------------------------------
# Test 7: Different fingerprints are independent
# ---------------------------------------------------------------------------


def test_fingerprints_are_independent() -> None:
    """Firing on fp_A does not pause fp_B."""
    rng = random.Random(7)
    cfg = _cfg(z_threshold=3.0, bins_required=3)
    recorder = CallbackRecorder()
    detector = ChangePointDetector(config=cfg, on_change_point=recorder)

    stored_mean = 400.0
    stored_std = 20.0
    shift = 100.0
    drift_bins = [60, 61, 62]

    # Fire on FP_A: all shifted samples
    for rpm_bin in drift_bins:
        rpm = float(rpm_bin * 100)
        stored_a = _make_stored_bin(_FP_A, rpm_bin, stored_mean, stored_std)
        for _ in range(25):
            detector.observe(
                _FP_A, 3, rpm, rng.gauss(stored_mean + shift, stored_std * 0.5), _NOW, stored_a
            )

    assert detector.is_paused(_FP_A)
    assert not detector.is_paused(_FP_B)

    # Feed some stable samples into FP_B — confirm it never gets paused
    stored_b = _make_stored_bin(_FP_B, 60, stored_mean, stored_std)
    for _ in range(10):
        detector.observe(_FP_B, 3, 6000.0, rng.gauss(stored_mean, stored_std * 0.5), _NOW, stored_b)

    assert not detector.is_paused(_FP_B)


# ---------------------------------------------------------------------------
# Test 8: Missing stored_bin skipped — no crash, no fire
# ---------------------------------------------------------------------------


def test_missing_stored_bin_no_crash_no_fire() -> None:
    """Observes with stored_bin=None should not crash; no fire is possible."""
    cfg = _cfg()
    recorder = CallbackRecorder()
    detector = ChangePointDetector(config=cfg, on_change_point=recorder)

    rng = random.Random(42)
    for _ in range(100):
        rpm = 6000.0 + rng.uniform(0, 500)
        detector.observe(_FP_A, 3, rpm, rng.gauss(400, 20), _NOW, None)

    assert len(recorder.events) == 0
    assert not detector.is_paused(_FP_A)


# ---------------------------------------------------------------------------
# Test 9: Stride is respected
# ---------------------------------------------------------------------------


def test_stride_gating() -> None:
    """With STRIDE=25, 24 deviating samples should NOT fire; adding the 25th triggers the test."""
    # Use a very low z_threshold so even moderate drift fires IF the test runs
    cfg = _cfg(z_threshold=0.5, bins_required=1)
    recorder = CallbackRecorder()
    detector = ChangePointDetector(config=cfg, on_change_point=recorder)

    stored_mean = 400.0
    stored_std = 20.0
    # Large, obvious drift
    shift = 200.0

    rpm_bin = 60
    rpm = 6000.0
    stored = _make_stored_bin(_FP_A, rpm_bin, stored_mean, stored_std)

    # Feed STRIDE-1 = 24 deviating samples
    stride = ChangePointDetector.WINDOW_STRIDE
    for _ in range(stride - 1):
        detector.observe(_FP_A, 3, rpm, stored_mean + shift, _NOW, stored)

    # No fire yet (stride not reached)
    assert len(recorder.events) == 0

    # Feed the stride-th sample — the test should now run and fire
    detector.observe(_FP_A, 3, rpm, stored_mean + shift, _NOW, stored)

    # Now with bins_required=1 and enormous drift, should have fired
    assert len(recorder.events) >= 1


# ---------------------------------------------------------------------------
# Test 10: Callback exception doesn't propagate
# ---------------------------------------------------------------------------


def test_callback_exception_does_not_propagate() -> None:
    """A callback that raises should be caught; subsequent observes still work."""

    class ExplodingCallback:
        def __call__(self, event: ChangePointEvent) -> None:
            raise RuntimeError("boom")

    cfg = _cfg(z_threshold=3.0, bins_required=3)
    detector = ChangePointDetector(config=cfg, on_change_point=ExplodingCallback())

    rng = random.Random(7)
    stored_mean = 400.0
    stored_std = 20.0
    shift = 100.0
    drift_bins = [60, 61, 62]

    # This should not raise even though callback does; all shifted to ensure fire
    for rpm_bin in drift_bins:
        rpm = float(rpm_bin * 100)
        stored = _make_stored_bin(_FP_A, rpm_bin, stored_mean, stored_std)
        for _ in range(25):
            detector.observe(
                _FP_A, 3, rpm, rng.gauss(stored_mean + shift, stored_std * 0.5), _NOW, stored
            )

    # Reset and try to observe again without crash
    detector.reset(_FP_A)
    stored = _make_stored_bin(_FP_A, 60, stored_mean, stored_std)
    detector.observe(_FP_A, 3, 6000.0, stored_mean, _NOW, stored)  # should not raise
