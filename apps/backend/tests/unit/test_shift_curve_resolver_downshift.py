"""Unit tests for ShiftCurveResolver.solve_optimal — downshift direction (FR-045, Task 13).

Tests cover the new `direction: Literal["up", "down"]` parameter:

1. Downshift with a moderate ratio jump finds a viable crossover within the
   [idle_rpm, max_rpm * r_g / r_{g-1}] interval.
2. Downshift with a larger ratio jump returns an RPM bounded by the tighter
   post_rpm_max ceiling.
3. Downshift with an impossible ratio jump (post_rpm_max < idle_rpm) returns
   None (unviable pair).
4. The existing upshift behaviour is unchanged when called with
   `direction="up"`.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

import pytest

from fh6.application.services.shift.curve_resolver import ShiftCurveResolver
from fh6.domain.ports.shift_predictor_repo import BinRecord
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint
from fh6.infrastructure.config import AppConfig

# ---------------------------------------------------------------------------
# Fixtures / helpers (mirror test_shift_curve_resolver.py)
# ---------------------------------------------------------------------------

_FP = EngineFingerprint(car_ordinal=2451, performance_index=812, num_cylinders=6)
_NOW = datetime(2026, 5, 23, 10, 0, 0, tzinfo=UTC)

IDLE_RPM = 900.0
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
    count: int = 100,
    m2: float = 100.0,
) -> BinRecord:
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
    rpm: float,
    peak_rpm: float = 6000.0,
    sigma: float = 1500.0,
    peak: float = 500.0,
) -> float:
    return peak * math.exp(-(((rpm - peak_rpm) / sigma) ** 2))


def _make_gaussian_bins(
    gear: int,
    peak_rpm: float = 6000.0,
    sigma: float = 1500.0,
    peak: float = 500.0,
    count: int = 100,
    rpm_range: tuple[int, int] = (10, 80),
) -> list[BinRecord]:
    bins = []
    for rpm_bin in range(rpm_range[0], rpm_range[1] + 1):
        center_rpm = (rpm_bin + 0.5) * 100.0
        q90 = _gaussian_torque(center_rpm, peak_rpm, sigma, peak)
        bins.append(_make_bin(gear=gear, rpm_bin=rpm_bin, q90=q90, count=count))
    return bins


@pytest.fixture
def cfg() -> AppConfig:
    return _make_config()


@pytest.fixture
def resolver(cfg: AppConfig) -> ShiftCurveResolver:
    return ShiftCurveResolver(config=cfg)


# ---------------------------------------------------------------------------
# Test 1: moderate downshift finds a viable crossover
# ---------------------------------------------------------------------------


def test_downshift_moderate_ratio_finds_crossover(resolver: ShiftCurveResolver) -> None:
    """Downshift from gear g (ratio=200) to gear g-1 (ratio=260).

    post_rpm_max = max_rpm * 200/260 ≈ 6153.8. Returned RPM must lie in
    [idle_rpm, 6154] (rounded to nearest 100).
    """
    bins_g = _make_gaussian_bins(gear=3, peak_rpm=6000.0, sigma=1500.0, peak=500.0)
    bins_gm1 = _make_gaussian_bins(gear=2, peak_rpm=6000.0, sigma=1500.0, peak=500.0)

    fit_g = resolver.fit_curve(bins_g, IDLE_RPM, MAX_RPM)
    fit_gm1 = resolver.fit_curve(bins_gm1, IDLE_RPM, MAX_RPM)
    assert fit_g is not None and fit_gm1 is not None

    ratio_g = 200.0
    ratio_gm1 = 260.0

    result = resolver.solve_optimal(
        fit_pre=fit_g,
        fit_post=fit_gm1,
        ratio_pre=ratio_g,
        ratio_post=ratio_gm1,
        direction="down",
        idle_rpm=IDLE_RPM,
        max_rpm=MAX_RPM,
    )

    assert result is not None, "Expected a viable downshift RPM, got None"
    assert isinstance(result, int)
    post_rpm_max = MAX_RPM * ratio_g / ratio_gm1  # ≈ 6153.8
    assert IDLE_RPM <= result <= post_rpm_max + 100, (
        f"Expected result in [{IDLE_RPM}, {post_rpm_max + 100}], got {result}"
    )
    assert result % 100 == 0


# ---------------------------------------------------------------------------
# Test 2: bigger ratio jump tightens the post_rpm_max ceiling
# ---------------------------------------------------------------------------


def test_downshift_large_ratio_caps_at_tight_post_rpm_max(
    resolver: ShiftCurveResolver,
) -> None:
    """ratio_gm1=320 → post_rpm_max = max_rpm * 200/320 = 5000.

    Returned RPM must be <= 5000.
    """
    bins_g = _make_gaussian_bins(gear=3, peak_rpm=6000.0, sigma=1500.0, peak=500.0)
    bins_gm1 = _make_gaussian_bins(gear=2, peak_rpm=6000.0, sigma=1500.0, peak=500.0)

    fit_g = resolver.fit_curve(bins_g, IDLE_RPM, MAX_RPM)
    fit_gm1 = resolver.fit_curve(bins_gm1, IDLE_RPM, MAX_RPM)
    assert fit_g is not None and fit_gm1 is not None

    ratio_g = 200.0
    ratio_gm1 = 320.0
    post_rpm_max = MAX_RPM * ratio_g / ratio_gm1  # = 5000.0

    result = resolver.solve_optimal(
        fit_pre=fit_g,
        fit_post=fit_gm1,
        ratio_pre=ratio_g,
        ratio_post=ratio_gm1,
        direction="down",
        idle_rpm=IDLE_RPM,
        max_rpm=MAX_RPM,
    )

    assert result is not None
    assert isinstance(result, int)
    assert result <= int(post_rpm_max), f"Expected result <= {int(post_rpm_max)}, got {result}"
    assert result >= IDLE_RPM


# ---------------------------------------------------------------------------
# Test 3: impossible jump → None
# ---------------------------------------------------------------------------


def test_downshift_impossible_jump_returns_none(resolver: ShiftCurveResolver) -> None:
    """ratio_gm1=1000 → post_rpm_max = 8000 * 200/1000 = 1600 RPM.

    With idle_rpm=900 this is theoretically viable (1600 > 900). To exercise
    the unviable branch we use ratio_gm1=2500 → post_rpm_max = 640 < 900.
    """
    bins_g = _make_gaussian_bins(gear=3, peak_rpm=6000.0, sigma=1500.0, peak=500.0)
    bins_gm1 = _make_gaussian_bins(gear=2, peak_rpm=6000.0, sigma=1500.0, peak=500.0)

    fit_g = resolver.fit_curve(bins_g, IDLE_RPM, MAX_RPM)
    fit_gm1 = resolver.fit_curve(bins_gm1, IDLE_RPM, MAX_RPM)
    assert fit_g is not None and fit_gm1 is not None

    ratio_g = 200.0
    # post_rpm_max = 8000 * 200 / 2500 = 640 < idle_rpm 900 → unviable
    ratio_gm1 = 2500.0
    post_rpm_max = MAX_RPM * ratio_g / ratio_gm1
    assert post_rpm_max < IDLE_RPM, "Sanity: this case should be unviable"

    result = resolver.solve_optimal(
        fit_pre=fit_g,
        fit_post=fit_gm1,
        ratio_pre=ratio_g,
        ratio_post=ratio_gm1,
        direction="down",
        idle_rpm=IDLE_RPM,
        max_rpm=MAX_RPM,
    )

    assert result is None, f"Expected None for unviable downshift, got {result}"


# ---------------------------------------------------------------------------
# Test 4: upshift case still works with explicit direction="up"
# ---------------------------------------------------------------------------


def test_upshift_with_explicit_direction_unchanged(resolver: ShiftCurveResolver) -> None:
    """Existing upshift scenario should keep working when invoked with
    direction="up" via the new keyword-only signature.
    """
    bins_g = _make_gaussian_bins(gear=3, peak_rpm=6000.0, sigma=1500.0, peak=500.0)
    bins_gp1 = _make_gaussian_bins(gear=4, peak_rpm=6000.0, sigma=1500.0, peak=500.0)

    fit_g = resolver.fit_curve(bins_g, IDLE_RPM, MAX_RPM)
    fit_gp1 = resolver.fit_curve(bins_gp1, IDLE_RPM, MAX_RPM)
    assert fit_g is not None and fit_gp1 is not None

    ratio_g = 200.0
    ratio_gp1 = 160.0

    result = resolver.solve_optimal(
        fit_pre=fit_g,
        fit_post=fit_gp1,
        ratio_pre=ratio_g,
        ratio_post=ratio_gp1,
        direction="up",
        idle_rpm=IDLE_RPM,
        max_rpm=MAX_RPM,
    )

    assert result is not None
    assert isinstance(result, int)
    assert IDLE_RPM <= result <= MAX_RPM
    assert result % 100 == 0
    # Same expectation as the v1 upshift test: crossover above the peak.
    assert result >= 6000, f"Expected upshift crossover >= 6000 RPM, got {result}"
