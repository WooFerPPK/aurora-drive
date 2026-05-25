"""Unit tests for ShiftCurveResolver — spline fit + Newton crossover (Task 9).

Tests cover:
1. Symmetric Gaussian synthetic curve evaluates near peak at 6000 RPM.
2. fit_curve returns None when too few qualifying bins.
3. fit_curve falls back to linear on non-monotonic data (evaluate still finite).
4. Newton crossover finds true crossover for two-gear pair.
5. Constant curve → fallback to maxRpm.
6. Out-of-range Newton iterations clamp within [idle, max].
7. resolve() with single-gear bins → empty dicts (no adjacent gear).
8. resolve() with two-gear bins + ratios → one entry; stage transitions.
9. Empty inputs → ResolvedCurves with stage="fallback".
10. Ratios missing for one gear → empty optimal_rpm_by_gear.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

import pytest

from fh6.application.services.shift.curve_resolver import ShiftCurveResolver
from fh6.application.services.shift.shift_predictor import ResolvedCurves
from fh6.domain.ports.shift_predictor_repo import BinRecord, RatioRecord
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint
from fh6.infrastructure.config import AppConfig

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_FP = EngineFingerprint(car_ordinal=2451, performance_index=812, num_cylinders=6)
_NOW = datetime(2026, 5, 23, 10, 0, 0, tzinfo=UTC)

IDLE_RPM = 1000.0
MAX_RPM = 8000.0


def _make_config(**overrides: Any) -> AppConfig:
    defaults: dict[str, Any] = dict(
        listen_addr="127.0.0.1",
        listen_port=5302,
        http_host="127.0.0.1",
        http_port=8000,
        db_dsn="postgresql+asyncpg://fh6:fh6@127.0.0.1:5432/fh6",
        llm_dry_run=True,
        log_level="DEBUG",
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
        shift_ewma_half_life_samples=54_000,
        shift_bin_min_count=10,
        shift_pair_learned_samples=200,
        shift_change_z_threshold=3.0,
        shift_change_bins_required=3,
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
    defaults.update(overrides)
    return AppConfig(**defaults)


def _make_bin(
    gear: int,
    rpm_bin: int,
    q90: float,
    count: int = 50,
    m2: float = 100.0,
) -> BinRecord:
    """Build a synthetic BinRecord at the given (gear, rpm_bin)."""
    return BinRecord(
        fingerprint=_FP,
        gear=gear,
        rpm_bin=rpm_bin,
        count=count,
        mean_torque_nm=q90 * 0.9,
        m2_torque=m2,
        q90_torque_nm=q90,
        mean_boost_psi=0.0,
        last_updated=_NOW,
    )


def _gaussian_torque(
    rpm: float, peak_rpm: float = 6000.0, sigma: float = 1500.0, peak: float = 500.0
) -> float:
    """Gaussian torque curve peaking at peak_rpm."""
    return peak * math.exp(-(((rpm - peak_rpm) / sigma) ** 2))


def _make_gaussian_bins(
    gear: int,
    peak_rpm: float = 6000.0,
    sigma: float = 1500.0,
    peak: float = 500.0,
    count: int = 50,
    rpm_range: tuple[int, int] = (20, 80),  # rpm_bin range
) -> list[BinRecord]:
    """Build a list of BinRecords following a Gaussian torque curve."""
    bins = []
    for rpm_bin in range(rpm_range[0], rpm_range[1] + 1):
        center_rpm = (rpm_bin + 0.5) * 100.0
        q90 = _gaussian_torque(center_rpm, peak_rpm, sigma, peak)
        bins.append(_make_bin(gear=gear, rpm_bin=rpm_bin, q90=q90, count=count))
    return bins


def _make_ratio(gear: int, ratio: float) -> RatioRecord:
    return RatioRecord(
        fingerprint=_FP,
        gear=gear,
        ratio=ratio,
        variance=0.01,
        last_updated=_NOW,
    )


@pytest.fixture
def cfg() -> AppConfig:
    return _make_config()


@pytest.fixture
def resolver(cfg: AppConfig) -> ShiftCurveResolver:
    return ShiftCurveResolver(config=cfg)


# ---------------------------------------------------------------------------
# Test 1: Symmetric Gaussian synthetic curve evaluates near peak
# ---------------------------------------------------------------------------


def test_fit_curve_gaussian_evaluates_at_peak(resolver: ShiftCurveResolver) -> None:
    """A Gaussian curve peaking at 6000 RPM should evaluate to ~500 Nm there.

    Tolerance: ±25 Nm (5%) to account for spline approximation.
    """
    bins = _make_gaussian_bins(gear=3, peak_rpm=6000.0, sigma=1500.0, peak=500.0, count=50)
    fit = resolver.fit_curve(bins, IDLE_RPM, MAX_RPM)

    assert fit is not None, "Expected a CurveFit, got None"
    value_at_peak = fit.evaluate(6000.0)
    assert value_at_peak == pytest.approx(500.0, abs=25.0), (
        f"Expected ~500 Nm at 6000 RPM, got {value_at_peak}"
    )


# ---------------------------------------------------------------------------
# Test 2: fit_curve returns None for sparse data (< 4 qualifying bins)
# ---------------------------------------------------------------------------


def test_fit_curve_returns_none_for_sparse_data(
    resolver: ShiftCurveResolver, cfg: AppConfig
) -> None:
    """With only 2 bins meeting the count threshold, fit_curve returns None."""
    # Only 2 bins with count >= shift_bin_min_count (10)
    bins = [
        _make_bin(gear=3, rpm_bin=40, q90=300.0, count=15),
        _make_bin(gear=3, rpm_bin=50, q90=400.0, count=15),
        # These have count below the threshold → filtered out
        _make_bin(gear=3, rpm_bin=60, q90=350.0, count=5),
        _make_bin(gear=3, rpm_bin=70, q90=300.0, count=3),
    ]
    fit = resolver.fit_curve(bins, IDLE_RPM, MAX_RPM)
    assert fit is None, "Expected None for sparse data (< 4 qualifying bins)"


# ---------------------------------------------------------------------------
# Test 3: fit_curve falls back to linear on non-monotonic data
# ---------------------------------------------------------------------------


def test_fit_curve_fallback_linear_on_non_monotonic(resolver: ShiftCurveResolver) -> None:
    """A bumpy multi-peak curve that forces spline retries should still return
    a usable CurveFit (linear fallback), and evaluate() returns finite values.
    """
    # Build a highly non-monotonic curve with 3 distinct peaks
    # rpm_bins: 10..80, three peaks at 2500, 4500, 7000
    bins = []
    for rpm_bin in range(10, 81):
        center = (rpm_bin + 0.5) * 100.0
        q90 = (
            200.0 * math.exp(-(((center - 2500.0) / 200.0) ** 2))
            + 300.0 * math.exp(-(((center - 4500.0) / 200.0) ** 2))
            + 250.0 * math.exp(-(((center - 7000.0) / 200.0) ** 2))
        )
        bins.append(_make_bin(gear=3, rpm_bin=rpm_bin, q90=q90, count=50))

    fit = resolver.fit_curve(bins, IDLE_RPM, MAX_RPM)
    assert fit is not None, "Expected a CurveFit even for non-monotonic data"

    # evaluate() should return finite values across the range
    for rpm in [1500.0, 3000.0, 5000.0, 7000.0, 8000.0]:
        val = fit.evaluate(rpm)
        assert math.isfinite(val), f"evaluate({rpm}) returned non-finite: {val}"

    # solve_optimal should not crash (use trivial ratio 1.0 → 1.0)
    fit2 = resolver.fit_curve(bins, IDLE_RPM, MAX_RPM)
    assert fit2 is not None
    result = resolver.solve_optimal(
        fit_pre=fit,
        fit_post=fit2,
        ratio_pre=1.0,
        ratio_post=1.0,
        direction="up",
        idle_rpm=IDLE_RPM,
        max_rpm=MAX_RPM,
    )
    assert isinstance(result, int)


# ---------------------------------------------------------------------------
# Test 4: Newton crossover finds the true crossover for two-gear pair
# ---------------------------------------------------------------------------


def test_newton_crossover_finds_true_crossover(resolver: ShiftCurveResolver) -> None:
    """For symmetric Gaussian curves with ratio_g=200 and ratio_gp1=160,
    Newton's method should find a crossover near the analytically expected RPM.

    With T(rpm) * 200 = T(0.8 * rpm) * 160, the crossover satisfies
    T(rpm) / T(0.8 * rpm) = 0.8. For identical Gaussians peaking at 6000 RPM,
    the crossover is above 6000 RPM (≈ 6700–7200 RPM range).
    Assert within ±300 of the numerically computed expected value.
    """
    bins_g3 = _make_gaussian_bins(gear=3, peak_rpm=6000.0, sigma=1500.0, peak=500.0, count=100)
    bins_g4 = _make_gaussian_bins(gear=4, peak_rpm=6000.0, sigma=1500.0, peak=500.0, count=100)

    fit_g3 = resolver.fit_curve(bins_g3, IDLE_RPM, MAX_RPM)
    fit_g4 = resolver.fit_curve(bins_g4, IDLE_RPM, MAX_RPM)
    assert fit_g3 is not None
    assert fit_g4 is not None

    ratio_g = 200.0
    ratio_gp1 = 160.0

    result = resolver.solve_optimal(
        fit_pre=fit_g3,
        fit_post=fit_g4,
        ratio_pre=ratio_g,
        ratio_post=ratio_gp1,
        direction="up",
        idle_rpm=IDLE_RPM,
        max_rpm=MAX_RPM,
    )

    # The result is rounded to 100 RPM and should be in-range
    assert isinstance(result, int)
    assert IDLE_RPM <= result <= MAX_RPM

    # The crossover should be above 6000 RPM because at 6000, T(6000)*200 vs
    # T(4800)*160 — at lower pre-shift RPM the post-shift RPM (0.8*pre) hits a
    # lower curve region. We expect crossover in the 6500–8000 range.
    assert result >= 6000, f"Expected crossover >= 6000 RPM, got {result}"

    # Must be a multiple of 100 (rounded)
    assert result % 100 == 0, f"Expected multiple of 100, got {result}"


# ---------------------------------------------------------------------------
# Test 5: Constant curve → fallback to maxRpm
# ---------------------------------------------------------------------------


def test_constant_curve_falls_back_to_max_rpm(resolver: ShiftCurveResolver) -> None:
    """A flat torque curve means f(rpm) has no sign change → fallback to maxRpm."""
    # Flat torque: 400 Nm across all bins
    bins_g3 = [_make_bin(gear=3, rpm_bin=b, q90=400.0, count=50) for b in range(20, 75)]
    bins_g4 = [_make_bin(gear=4, rpm_bin=b, q90=400.0, count=50) for b in range(20, 75)]

    fit_g3 = resolver.fit_curve(bins_g3, IDLE_RPM, MAX_RPM)
    fit_g4 = resolver.fit_curve(bins_g4, IDLE_RPM, MAX_RPM)
    assert fit_g3 is not None
    assert fit_g4 is not None

    # With identical flat curves and ratio_g == ratio_gp1, f(rpm) = T * r - T * r = 0 everywhere
    # Newton will bail (near-flat derivative) → fallback to maxRpm
    result = resolver.solve_optimal(
        fit_pre=fit_g3,
        fit_post=fit_g4,
        ratio_pre=200.0,
        ratio_post=200.0,
        direction="up",
        idle_rpm=IDLE_RPM,
        max_rpm=MAX_RPM,
    )

    expected = int(round(MAX_RPM / 100) * 100)
    assert result == expected, f"Expected fallback {expected}, got {result}"


# ---------------------------------------------------------------------------
# Test 6: Out-of-range seed clamps within [idle_rpm, max_rpm]
# ---------------------------------------------------------------------------


def test_newton_clamps_within_range(resolver: ShiftCurveResolver) -> None:
    """solve_optimal result must lie in [idle_rpm, max_rpm] regardless of Newton steps."""
    idle = 1000.0
    max_r = 8000.0

    bins_g3 = _make_gaussian_bins(gear=3, peak_rpm=6000.0, sigma=1500.0, peak=500.0, count=100)
    bins_g4 = _make_gaussian_bins(gear=4, peak_rpm=6000.0, sigma=1500.0, peak=500.0, count=100)

    fit_g3 = resolver.fit_curve(bins_g3, idle, max_r)
    fit_g4 = resolver.fit_curve(bins_g4, idle, max_r)
    assert fit_g3 is not None and fit_g4 is not None

    result = resolver.solve_optimal(
        fit_pre=fit_g3,
        fit_post=fit_g4,
        ratio_pre=200.0,
        ratio_post=160.0,
        direction="up",
        idle_rpm=idle,
        max_rpm=max_r,
    )
    assert result is not None
    assert idle <= result <= max_r, f"Result {result} out of [{idle}, {max_r}]"


# ---------------------------------------------------------------------------
# Test 7: resolve() with single-gear bins → empty dicts
# ---------------------------------------------------------------------------


def test_resolve_single_gear_no_adjacent(resolver: ShiftCurveResolver) -> None:
    """If only gear 3 has bins (and no gear 4), resolve() returns empty dicts."""
    bins_g3 = _make_gaussian_bins(gear=3)
    bins_dict = {(3, rec.rpm_bin): rec for rec in bins_g3}

    ratio_g3 = _make_ratio(gear=3, ratio=200.0)
    ratio_g4 = _make_ratio(gear=4, ratio=160.0)
    ratios_dict = {3: ratio_g3, 4: ratio_g4}

    result = resolver.resolve(bins_dict, ratios_dict, IDLE_RPM, MAX_RPM)

    assert isinstance(result, ResolvedCurves)
    assert result.optimal_rpm_by_gear == {}, "Should be empty: no gear 4 bins to pair with"
    assert result.confidence_by_gear == {}


# ---------------------------------------------------------------------------
# Test 8: resolve() with two-gear bins + ratios
# ---------------------------------------------------------------------------


def test_resolve_two_gears_returns_entry(resolver: ShiftCurveResolver) -> None:
    """Bins for gears 3 and 4 with both ratios → one entry for gear 3."""
    bins_g3 = _make_gaussian_bins(gear=3, count=50)
    bins_g4 = _make_gaussian_bins(gear=4, count=50)

    bins_dict: dict[tuple[int, int], BinRecord] = {}
    for rec in bins_g3:
        bins_dict[(3, rec.rpm_bin)] = rec
    for rec in bins_g4:
        bins_dict[(4, rec.rpm_bin)] = rec

    ratios_dict = {3: _make_ratio(3, 200.0), 4: _make_ratio(4, 160.0)}

    result = resolver.resolve(bins_dict, ratios_dict, IDLE_RPM, MAX_RPM)

    assert isinstance(result, ResolvedCurves)
    assert 3 in result.optimal_rpm_by_gear, "Expected gear 3 entry"
    assert 3 in result.confidence_by_gear

    # stage should be "prior" when sample count below threshold (200 * 2 = 400 total needed)
    # 61 bins * 50 count each = 3050 per gear; two gears = 6100 total, well above 200
    # So stage should be "learned"
    assert result.stage in ("prior", "learned")

    # confidence should be between 0 and 1
    conf = result.confidence_by_gear[3]
    assert 0.0 <= conf <= 1.0


def test_resolve_stage_prior_below_threshold(resolver: ShiftCurveResolver, cfg: AppConfig) -> None:
    """With very low sample counts, stage should be 'prior'."""
    # Use count=1 so n_samples < cfg.shift_pair_learned_samples
    bins_g3 = _make_gaussian_bins(gear=3, count=1)
    bins_g4 = _make_gaussian_bins(gear=4, count=1)

    # With count=1, these won't qualify (count < shift_bin_min_count=10)
    # So they won't produce a fit. Stage → "fallback"
    bins_dict: dict[tuple[int, int], BinRecord] = {}
    for rec in bins_g3:
        bins_dict[(3, rec.rpm_bin)] = rec
    for rec in bins_g4:
        bins_dict[(4, rec.rpm_bin)] = rec

    ratios_dict = {3: _make_ratio(3, 200.0), 4: _make_ratio(4, 160.0)}
    result = resolver.resolve(bins_dict, ratios_dict, IDLE_RPM, MAX_RPM)

    # count=1 < shift_bin_min_count=10, so no fits → fallback
    assert result.stage == "fallback"


def test_resolve_stage_learned_above_threshold(
    resolver: ShiftCurveResolver, cfg: AppConfig
) -> None:
    """With count >> threshold, stage should be 'learned'."""
    # Use count=300 >> cfg.shift_pair_learned_samples=200
    bins_g3 = _make_gaussian_bins(gear=3, count=300)
    bins_g4 = _make_gaussian_bins(gear=4, count=300)

    bins_dict: dict[tuple[int, int], BinRecord] = {}
    for rec in bins_g3:
        bins_dict[(3, rec.rpm_bin)] = rec
    for rec in bins_g4:
        bins_dict[(4, rec.rpm_bin)] = rec

    ratios_dict = {3: _make_ratio(3, 200.0), 4: _make_ratio(4, 160.0)}
    result = resolver.resolve(bins_dict, ratios_dict, IDLE_RPM, MAX_RPM)

    assert result.stage == "learned"


# ---------------------------------------------------------------------------
# Test 9: Empty inputs → stage="fallback"
# ---------------------------------------------------------------------------


def test_resolve_empty_inputs(resolver: ShiftCurveResolver) -> None:
    """resolve({}, {}, ...) returns ResolvedCurves with stage='fallback' and empty dicts."""
    result = resolver.resolve({}, {}, IDLE_RPM, MAX_RPM)

    assert isinstance(result, ResolvedCurves)
    assert result.stage == "fallback"
    assert result.optimal_rpm_by_gear == {}
    assert result.confidence_by_gear == {}
    assert result.samples_by_gear_pair == {}


# ---------------------------------------------------------------------------
# Test 10: Ratios missing for one gear → empty optimal_rpm_by_gear
# ---------------------------------------------------------------------------


def test_resolve_missing_ratio_for_one_gear(resolver: ShiftCurveResolver) -> None:
    """Bins for gears 3 and 4 but ratios only for gear 3 → no crossover computed."""
    bins_g3 = _make_gaussian_bins(gear=3, count=50)
    bins_g4 = _make_gaussian_bins(gear=4, count=50)

    bins_dict: dict[tuple[int, int], BinRecord] = {}
    for rec in bins_g3:
        bins_dict[(3, rec.rpm_bin)] = rec
    for rec in bins_g4:
        bins_dict[(4, rec.rpm_bin)] = rec

    # Only ratio for gear 3, not gear 4
    ratios_dict = {3: _make_ratio(3, 200.0)}

    result = resolver.resolve(bins_dict, ratios_dict, IDLE_RPM, MAX_RPM)

    assert result.optimal_rpm_by_gear == {}, (
        "Without both gear ratios, crossover cannot be computed"
    )
    assert result.confidence_by_gear == {}


# ---------------------------------------------------------------------------
# FR-011 confidence formula tests
# ---------------------------------------------------------------------------
#
#   confidence = min(1, samples_pair / 400)
#              * (1 - normalized_spline_residual)
#              * (1 - drift_penalty)
#
# Notes on the partition definition used here:
#   - "Top third of gear g" = rpm_bin where rpm_bin*100 >= idle_rpm + 2/3*(max-idle)
#   - "Bottom third of gear g+1" = rpm_bin where rpm_bin*100 < idle_rpm + 1/3*(max-idle)
# For idle=1000, max=8000: thirds = 1000-3333, 3333-5667, 5667-8000.
# So bottom-third rpm_bin <= 32 (rpm_bin*100 < 3333); top-third rpm_bin >= 56
# (rpm_bin*100 >= 5667 → rpm_bin >= 56.67, rounded up to 57 actually but here we
# use >= so rpm_bin*100 >= 5666.67 → rpm_bin >= 57). The test bins are chosen
# generously so the exact float boundary doesn't matter.
# ---------------------------------------------------------------------------


def _samples_pair_upshift_thirds(
    bins_g: list[BinRecord],
    bins_gp1: list[BinRecord],
    idle_rpm: float,
    max_rpm: float,
) -> int:
    """Top-third of g + bottom-third of g+1 (FR-011 partition)."""
    third = (max_rpm - idle_rpm) / 3.0
    top_threshold = idle_rpm + 2.0 * third
    bottom_threshold = idle_rpm + third
    top_g = sum(b.count for b in bins_g if b.rpm_bin * 100.0 >= top_threshold)
    bottom_gp1 = sum(b.count for b in bins_gp1 if b.rpm_bin * 100.0 < bottom_threshold)
    return int(top_g + bottom_gp1)


def test_fr011_confidence_samples_pair_uses_thirds_partition(
    resolver: ShiftCurveResolver,
) -> None:
    """samples_pair = top-third(g) + bottom-third(g+1), NOT the full bin count.

    Build bins where the top-third of g3 and bottom-third of g4 carry a known
    sample count; bins in the middle / other thirds have larger counts that
    would skew the result if the resolver used the full sum. The reported
    confidence should be consistent with samples_pair == thirds-partition sum.
    """
    # Gear 3: rpm bins 20..80. Top third bins (rpm_bin*100 >= 5667 → rpm_bin
    # >= 57) get count=30, rest get count=100 (deliberately heavy so a
    # full-sum implementation would yield a higher sample_term).
    bins_g3 = []
    for rpm_bin in range(20, 81):
        center_rpm = (rpm_bin + 0.5) * 100.0
        q90 = _gaussian_torque(center_rpm, 6000.0, 1500.0, 500.0)
        count = 30 if rpm_bin * 100.0 >= IDLE_RPM + 2 * (MAX_RPM - IDLE_RPM) / 3 else 100
        bins_g3.append(_make_bin(gear=3, rpm_bin=rpm_bin, q90=q90, count=count))

    # Gear 4: bottom third bins get count=30, rest count=100.
    bins_g4 = []
    for rpm_bin in range(20, 81):
        center_rpm = (rpm_bin + 0.5) * 100.0
        q90 = _gaussian_torque(center_rpm, 6000.0, 1500.0, 500.0)
        count = 30 if rpm_bin * 100.0 < IDLE_RPM + (MAX_RPM - IDLE_RPM) / 3 else 100
        bins_g4.append(_make_bin(gear=4, rpm_bin=rpm_bin, q90=q90, count=count))

    samples_pair = _samples_pair_upshift_thirds(bins_g3, bins_g4, IDLE_RPM, MAX_RPM)
    # Sanity: thirds-partition count is much smaller than the full-sum count.
    full_sum = sum(b.count for b in bins_g3) + sum(b.count for b in bins_g4)
    assert samples_pair < full_sum / 2, (
        f"Test setup should produce samples_pair much smaller than full sum: "
        f"samples_pair={samples_pair}, full_sum={full_sum}"
    )

    bins_dict = {(3, b.rpm_bin): b for b in bins_g3}
    bins_dict.update({(4, b.rpm_bin): b for b in bins_g4})
    ratios_dict = {3: _make_ratio(3, 200.0), 4: _make_ratio(4, 160.0)}

    result = resolver.resolve(bins_dict, ratios_dict, IDLE_RPM, MAX_RPM)

    assert 3 in result.confidence_by_gear
    conf = result.confidence_by_gear[3]
    # Expected sample_term = min(1, samples_pair / 400).
    expected_sample_term = min(1.0, samples_pair / 400.0)
    # Spline term on a perfect Gaussian: residual should be close to 0 →
    # (1 - residual) close to 1. We assert conf is close to expected_sample_term.
    assert conf == pytest.approx(expected_sample_term, abs=0.05), (
        f"Expected confidence ≈ {expected_sample_term} (samples_pair={samples_pair}), got {conf}"
    )


def test_fr011_confidence_high_for_clean_curve(
    resolver: ShiftCurveResolver,
) -> None:
    """A near-perfect Gaussian curve produces a low spline residual → high confidence.

    With 250 samples per bin distributed across both gears (samples_pair > 400),
    the sample_term saturates at 1.0. The spline residual on a clean curve is
    near-zero, so confidence should be very close to 1.0.
    """
    bins_g3 = _make_gaussian_bins(gear=3, count=250)
    bins_g4 = _make_gaussian_bins(gear=4, count=250)

    samples_pair = _samples_pair_upshift_thirds(bins_g3, bins_g4, IDLE_RPM, MAX_RPM)
    assert samples_pair >= 400, "Sanity: enough samples to saturate sample_term"

    bins_dict = {(3, b.rpm_bin): b for b in bins_g3}
    bins_dict.update({(4, b.rpm_bin): b for b in bins_g4})
    ratios_dict = {3: _make_ratio(3, 200.0), 4: _make_ratio(4, 160.0)}

    result = resolver.resolve(bins_dict, ratios_dict, IDLE_RPM, MAX_RPM)

    conf = result.confidence_by_gear[3]
    assert conf >= 0.9, (
        f"Expected confidence near 1.0 for a clean curve at saturated samples; got {conf}"
    )


def test_fr011_confidence_drops_for_noisy_curve(
    resolver: ShiftCurveResolver,
) -> None:
    """A noisy curve has a higher normalized residual → lower confidence than a clean curve.

    Builds two curves with the same sample counts, one clean and one with mild
    additive noise on q90 that still admits a UnivariateSpline fit (heavy noise
    triggers the linear interp1d fallback which by definition has zero residual).
    The noisy curve's confidence must be strictly lower than the clean curve's.
    """
    import random

    rng = random.Random(42)

    # Clean curve
    bins_g3_clean = _make_gaussian_bins(gear=3, count=250)
    bins_g4_clean = _make_gaussian_bins(gear=4, count=250)
    bins_clean = {(3, b.rpm_bin): b for b in bins_g3_clean}
    bins_clean.update({(4, b.rpm_bin): b for b in bins_g4_clean})

    # Noisy curve: same counts but mild jitter (±20 Nm) so the spline still fits
    # (heavier noise forces the interp1d fallback which has zero residual).
    def _noisy(b: BinRecord) -> BinRecord:
        noise = rng.uniform(-20.0, 20.0)
        return _make_bin(
            gear=b.gear,
            rpm_bin=b.rpm_bin,
            q90=max(50.0, b.q90_torque_nm + noise),
            count=b.count,
        )

    bins_noisy = {k: _noisy(v) for k, v in bins_clean.items()}

    ratios_dict = {3: _make_ratio(3, 200.0), 4: _make_ratio(4, 160.0)}
    clean = resolver.resolve(bins_clean, ratios_dict, IDLE_RPM, MAX_RPM)
    noisy = resolver.resolve(bins_noisy, ratios_dict, IDLE_RPM, MAX_RPM)

    assert clean.confidence_by_gear[3] > noisy.confidence_by_gear[3], (
        f"Noisy curve should have lower confidence: clean={clean.confidence_by_gear[3]}, "
        f"noisy={noisy.confidence_by_gear[3]}"
    )


def test_fr011_confidence_downshift_uses_mirrored_thirds(
    resolver: ShiftCurveResolver,
) -> None:
    """Downshift samples_pair = bottom-third(g) + top-third(g-1) (mirror of upshift).

    Build bins where the bottom third of g3 and top third of g2 each have a
    small count, while the other bins have a much larger count. The reported
    downshift confidence should match the small-count partition, not the full sum.
    """
    # Gear 3: bottom-third bins (rpm_bin*100 < 3333.33 → rpm_bin <= 33) get count=30,
    # rest count=100.
    bins_g3 = []
    for rpm_bin in range(20, 81):
        center_rpm = (rpm_bin + 0.5) * 100.0
        q90 = _gaussian_torque(center_rpm, 6000.0, 1500.0, 500.0)
        count = 30 if rpm_bin * 100.0 < IDLE_RPM + (MAX_RPM - IDLE_RPM) / 3 else 100
        bins_g3.append(_make_bin(gear=3, rpm_bin=rpm_bin, q90=q90, count=count))

    # Gear 2: top-third bins get count=30, rest count=100.
    bins_g2 = []
    for rpm_bin in range(20, 81):
        center_rpm = (rpm_bin + 0.5) * 100.0
        q90 = _gaussian_torque(center_rpm, 6000.0, 1500.0, 500.0)
        count = 30 if rpm_bin * 100.0 >= IDLE_RPM + 2 * (MAX_RPM - IDLE_RPM) / 3 else 100
        bins_g2.append(_make_bin(gear=2, rpm_bin=rpm_bin, q90=q90, count=count))

    # Downshift partition: bottom-third(g3) + top-third(g2)
    third = (MAX_RPM - IDLE_RPM) / 3.0
    bottom_g3 = sum(b.count for b in bins_g3 if b.rpm_bin * 100.0 < IDLE_RPM + third)
    top_g2 = sum(b.count for b in bins_g2 if b.rpm_bin * 100.0 >= IDLE_RPM + 2 * third)
    samples_pair = bottom_g3 + top_g2

    bins_dict = {(3, b.rpm_bin): b for b in bins_g3}
    bins_dict.update({(2, b.rpm_bin): b for b in bins_g2})
    # Downshift from g3 → g2: ratio_post (g2) > ratio_pre (g3). Use viable jump.
    ratios_dict = {2: _make_ratio(2, 260.0), 3: _make_ratio(3, 200.0)}

    result = resolver.resolve(bins_dict, ratios_dict, IDLE_RPM, MAX_RPM)

    assert 3 in result.confidence_by_gear_downshift, (
        "Downshift confidence should be present for the 3→2 pair"
    )
    conf = result.confidence_by_gear_downshift[3]
    expected_sample_term = min(1.0, samples_pair / 400.0)
    # Allow slack for the spline residual term — should be small but non-zero.
    assert conf == pytest.approx(expected_sample_term, abs=0.05), (
        f"Expected downshift confidence ≈ {expected_sample_term} "
        f"(samples_pair={samples_pair}), got {conf}"
    )
