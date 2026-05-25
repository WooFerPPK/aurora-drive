"""Unit tests for TransmissionModeInferer (FR-041).

Five scenarios:
1. Auto-shift pattern (tight RPM cluster) → infer returns ("auto", confidence > 0.3).
2. Manual-shift pattern (wide RPM dispersion) → infer returns ("manual", confidence ≥ 0.4).
3. Fewer than min_samples → infer returns ("unknown", 0.0).
4. 1→2 upshifts at wild RPMs are excluded; only 2→3+ pairs feed the stdev.
5. Two distinct fingerprints don't cross-contaminate.
"""

from __future__ import annotations

from fh6.application.services.shift.transmission_mode import (
    TransmissionModeInferer,
)
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint
from fh6.infrastructure.config import AppConfig

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_FP_A = EngineFingerprint(car_ordinal=2451, performance_index=812, num_cylinders=6)
_FP_B = EngineFingerprint(car_ordinal=9999, performance_index=700, num_cylinders=4)

# Minimal config with all required fields stubbed to benign values.
_BASE_CFG_KWARGS: dict = dict(
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
    rewind_yaw_tolerance_rad=1.5707963267948966,
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


def _make_cfg(**overrides) -> AppConfig:
    kwargs = dict(_BASE_CFG_KWARGS)
    kwargs.update(overrides)
    return AppConfig(**kwargs)


def _make_inferer(**cfg_overrides) -> TransmissionModeInferer:
    return TransmissionModeInferer(config=_make_cfg(**cfg_overrides))


# ---------------------------------------------------------------------------
# 1. Auto-shift pattern: 12 upshifts at gear pair (3→4), all RPMs within ±10
#    of 7000 → after ≥10 samples infer returns ("auto", confidence > 0.3).
# ---------------------------------------------------------------------------


class TestAutoShiftDetection:
    def test_auto_mode_returned_after_ten_samples(self) -> None:
        inferer = _make_inferer()
        # All pre-shift RPMs clustered tightly around 7000 (stdev << 50)
        tight_rpms = [
            7000.0,
            7005.0,
            6995.0,
            7008.0,
            6992.0,
            7003.0,
            6997.0,
            7010.0,
            6990.0,
            7002.0,
            6998.0,
            7004.0,
        ]
        for rpm in tight_rpms:
            inferer.observe_clean_upshift(_FP_A, gear_from=3, gear_to=4, pre_shift_rpm=rpm)

        result = inferer.infer(_FP_A)
        assert result.mode == "auto"
        assert result.confidence > 0.3
        assert result.sample_count == 12


# ---------------------------------------------------------------------------
# 2. Manual-shift pattern: 12 upshifts with high stdev (~500 RPM) →
#    infer returns ("manual", confidence ≥ 0.4).
# ---------------------------------------------------------------------------


class TestManualShiftDetection:
    def test_manual_mode_returned_for_wide_dispersion(self) -> None:
        inferer = _make_inferer()
        # RPMs with stdev ~500 — clearly manual
        manual_rpms = [
            5500.0,
            6200.0,
            5800.0,
            6800.0,
            6100.0,
            6500.0,
            5400.0,
            6900.0,
            6000.0,
            5700.0,
            6400.0,
            6300.0,
        ]
        for rpm in manual_rpms:
            inferer.observe_clean_upshift(_FP_A, gear_from=3, gear_to=4, pre_shift_rpm=rpm)

        result = inferer.infer(_FP_A)
        assert result.mode == "manual"
        assert result.confidence >= 0.4
        assert result.sample_count == 12


# ---------------------------------------------------------------------------
# 3. Fewer than min_samples (5 upshifts) → ("unknown", 0.0).
# ---------------------------------------------------------------------------


class TestInsufficientSamples:
    def test_unknown_when_fewer_than_min_samples(self) -> None:
        inferer = _make_inferer()
        for rpm in [7000.0, 7005.0, 6995.0, 7008.0, 6992.0]:
            inferer.observe_clean_upshift(_FP_A, gear_from=3, gear_to=4, pre_shift_rpm=rpm)

        result = inferer.infer(_FP_A)
        assert result.mode == "unknown"
        assert result.confidence == 0.0
        assert result.sample_count == 5


# ---------------------------------------------------------------------------
# 4. 1→2 upshifts at wildly different RPMs must be excluded.
#    Mix in 1→2 at extreme RPMs alongside tight 2→3 and 3→4 pairs; the
#    inferer should still return "auto" because only gear_from ≥ 2 counts.
# ---------------------------------------------------------------------------


class TestOneToTwoExclusion:
    def test_one_to_two_excluded_from_dispersion(self) -> None:
        inferer = _make_inferer()

        # Feed tight samples for 2→3 and 3→4
        tight_rpms = [
            7000.0,
            7005.0,
            6995.0,
            7008.0,
            6992.0,
            7003.0,
            6997.0,
            7010.0,
            6990.0,
            7002.0,
            6998.0,
            7004.0,
        ]
        for rpm in tight_rpms:
            inferer.observe_clean_upshift(_FP_A, gear_from=2, gear_to=3, pre_shift_rpm=rpm)
            inferer.observe_clean_upshift(_FP_A, gear_from=3, gear_to=4, pre_shift_rpm=rpm)

        # Now inject 1→2 upshifts at very different RPMs that would wreck stdev
        for rpm in [3000.0, 9000.0, 3500.0]:
            inferer.observe_clean_upshift(_FP_A, gear_from=1, gear_to=2, pre_shift_rpm=rpm)

        result = inferer.infer(_FP_A)
        # 1→2 samples are ignored; the clean 2→3 and 3→4 tight samples dominate
        assert result.mode == "auto"
        # sample_count counts only the non-1→2 samples actually stored
        assert result.sample_count == 24


# ---------------------------------------------------------------------------
# 5. Two fingerprints' samples don't cross-contaminate.
#    FP_A → auto pattern; FP_B → manual pattern.
# ---------------------------------------------------------------------------


class TestFingerprintIsolation:
    def test_two_fingerprints_independent(self) -> None:
        inferer = _make_inferer()

        # FP_A: tight cluster → auto
        for rpm in [
            7000.0,
            7005.0,
            6995.0,
            7008.0,
            6992.0,
            7003.0,
            6997.0,
            7010.0,
            6990.0,
            7002.0,
            6998.0,
            7004.0,
        ]:
            inferer.observe_clean_upshift(_FP_A, gear_from=3, gear_to=4, pre_shift_rpm=rpm)

        # FP_B: wide dispersion → manual
        for rpm in [
            5500.0,
            6200.0,
            5800.0,
            6800.0,
            6100.0,
            6500.0,
            5400.0,
            6900.0,
            6000.0,
            5700.0,
            6400.0,
            6300.0,
        ]:
            inferer.observe_clean_upshift(_FP_B, gear_from=3, gear_to=4, pre_shift_rpm=rpm)

        result_a = inferer.infer(_FP_A)
        result_b = inferer.infer(_FP_B)

        assert result_a.mode == "auto"
        assert result_b.mode == "manual"
        # Neither fingerprint's data should influence the other
        assert result_a.sample_count == 12
        assert result_b.sample_count == 12
