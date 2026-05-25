"""Tests for shift predictor config fields in AppConfig."""

import os
from unittest.mock import patch

import pytest

from fh6.infrastructure.config import load_from_env


class TestShiftConfigDefaults:
    """Test that shift config fields load with documented defaults when env unset."""

    def test_shift_defaults_present_when_env_unset(self):
        """All FH6_SHIFT_* env vars unset -> defaults apply."""
        shift_env_vars = {
            "FH6_SHIFT_THROTTLE_MIN",
            "FH6_SHIFT_BRAKE_MAX",
            "FH6_SHIFT_STEER_MAX",
            "FH6_SHIFT_COMBINED_SLIP_MAX",
            "FH6_SHIFT_GEAR_STABLE_FRAMES",
            "FH6_SHIFT_WARMUP_SECONDS",
            "FH6_SHIFT_BOOST_SETTLE_PSI_PER_S",
            "FH6_SHIFT_EWMA_HALF_LIFE_SAMPLES",
            "FH6_SHIFT_BIN_MIN_COUNT",
            "FH6_SHIFT_PAIR_LEARNED_SAMPLES",
            "FH6_SHIFT_CHANGE_Z_THRESHOLD",
            "FH6_SHIFT_CHANGE_BINS_REQUIRED",
            "FH6_SHIFT_RECOMPUTE_EVERY_N",
            "FH6_SHIFT_DISPLAY_THROTTLE_MIN",
            "FH6_SHIFT_TURBO_RESIDUAL_DELAY_MS",
            "FH6_SHIFT_NA_RESIDUAL_DELAY_MS",
            "FH6_SHIFT_RESIDUAL_WINDOW_MS",
        }

        # Create a copy of environ and remove all shift vars
        clean_env = dict(os.environ)
        for var in shift_env_vars:
            clean_env.pop(var, None)

        with patch.dict(os.environ, clean_env, clear=True):
            config = load_from_env()

        # Check all defaults
        assert config.shift_throttle_min == pytest.approx(0.95)
        assert config.shift_brake_max == pytest.approx(0.05)
        assert config.shift_steer_max == pytest.approx(0.10)
        assert config.shift_combined_slip_max == pytest.approx(0.20)
        assert config.shift_gear_stable_frames == 5
        assert config.shift_warmup_seconds == 60
        assert config.shift_boost_settle_psi_per_s == pytest.approx(1.0)
        assert config.shift_ewma_half_life_samples == 54000
        assert config.shift_bin_min_count == 10
        assert config.shift_pair_learned_samples == 200
        assert config.shift_change_z_threshold == pytest.approx(3.0)
        assert config.shift_change_bins_required == 3
        assert config.shift_recompute_every_n == 50
        assert config.shift_display_throttle_min == pytest.approx(0.70)
        assert config.shift_turbo_residual_delay_ms == 500
        assert config.shift_na_residual_delay_ms == 300
        assert config.shift_residual_window_ms == 200

    def test_shift_env_overrides(self):
        """All FH6_SHIFT_* env vars set -> overrides apply."""
        overrides = {
            "FH6_SHIFT_THROTTLE_MIN": "0.85",
            "FH6_SHIFT_BRAKE_MAX": "0.15",
            "FH6_SHIFT_STEER_MAX": "0.25",
            "FH6_SHIFT_COMBINED_SLIP_MAX": "0.35",
            "FH6_SHIFT_GEAR_STABLE_FRAMES": "10",
            "FH6_SHIFT_WARMUP_SECONDS": "120",
            "FH6_SHIFT_BOOST_SETTLE_PSI_PER_S": "2.0",
            "FH6_SHIFT_EWMA_HALF_LIFE_SAMPLES": "100000",
            "FH6_SHIFT_BIN_MIN_COUNT": "20",
            "FH6_SHIFT_PAIR_LEARNED_SAMPLES": "500",
            "FH6_SHIFT_CHANGE_Z_THRESHOLD": "2.5",
            "FH6_SHIFT_CHANGE_BINS_REQUIRED": "5",
            "FH6_SHIFT_RECOMPUTE_EVERY_N": "100",
            "FH6_SHIFT_DISPLAY_THROTTLE_MIN": "0.50",
            "FH6_SHIFT_TURBO_RESIDUAL_DELAY_MS": "1000",
            "FH6_SHIFT_NA_RESIDUAL_DELAY_MS": "600",
            "FH6_SHIFT_RESIDUAL_WINDOW_MS": "400",
        }

        with patch.dict(os.environ, overrides, clear=False):
            config = load_from_env()

        assert config.shift_throttle_min == pytest.approx(0.85)
        assert config.shift_brake_max == pytest.approx(0.15)
        assert config.shift_steer_max == pytest.approx(0.25)
        assert config.shift_combined_slip_max == pytest.approx(0.35)
        assert config.shift_gear_stable_frames == 10
        assert config.shift_warmup_seconds == 120
        assert config.shift_boost_settle_psi_per_s == pytest.approx(2.0)
        assert config.shift_ewma_half_life_samples == 100000
        assert config.shift_bin_min_count == 20
        assert config.shift_pair_learned_samples == 500
        assert config.shift_change_z_threshold == pytest.approx(2.5)
        assert config.shift_change_bins_required == 5
        assert config.shift_recompute_every_n == 100
        assert config.shift_display_throttle_min == pytest.approx(0.50)
        assert config.shift_turbo_residual_delay_ms == 1000
        assert config.shift_na_residual_delay_ms == 600
        assert config.shift_residual_window_ms == 400
