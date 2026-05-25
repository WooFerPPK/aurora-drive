"""Tests for shift predictor v2 config fields in AppConfig."""

import os
from unittest.mock import patch

import pytest

from fh6.infrastructure.config import AppConfig, load_from_env


class TestShiftV2ConfigDefaults:
    """Test that shift v2 config fields load with documented defaults when env unset."""

    def test_shift_v2_defaults_present_when_env_unset(self):
        """All FH6_SHIFT_* v2 env vars unset -> defaults apply."""
        shift_v2_env_vars = {
            "FH6_SHIFT_PRIOR_REBUILD_COOLDOWN_S",
            "FH6_SHIFT_PRIOR_MIN_FP_SAMPLES",
            "FH6_SHIFT_TCS_SLIP_THRESHOLD",
            "FH6_SHIFT_TCS_TORQUE_FLOOR_RATIO",
            "FH6_SHIFT_ASSIST_ALERT_PCT",
            "FH6_SHIFT_ASSIST_RECENT_WINDOW",
            "FH6_SHIFT_TRANS_MODE_RING_CAP",
            "FH6_SHIFT_TRANS_MODE_MIN_SAMPLES",
            "FH6_SHIFT_TRANS_MODE_AUTO_STDEV_RPM",
            "FH6_SHIFT_DOWNSHIFT_BRAKE_DISPLAY_MIN",
            "FH6_SHIFT_DOWNSHIFT_THROTTLE_DISPLAY_MAX",
        }

        # Create a copy of environ and remove all v2 shift vars
        clean_env = dict(os.environ)
        for var in shift_v2_env_vars:
            clean_env.pop(var, None)

        with patch.dict(os.environ, clean_env, clear=True):
            config = load_from_env()

        # Check all v2 defaults
        assert config.shift_prior_rebuild_cooldown_s == 300
        assert config.shift_prior_min_fp_samples == 1000
        assert config.shift_tcs_slip_threshold == pytest.approx(0.50)
        assert config.shift_tcs_torque_floor_ratio == pytest.approx(0.85)
        assert config.shift_assist_alert_pct == pytest.approx(0.05)
        assert config.shift_assist_recent_window == 900
        assert config.shift_trans_mode_ring_cap == 30
        assert config.shift_trans_mode_min_samples == 10
        assert config.shift_trans_mode_auto_stdev_rpm == pytest.approx(50.0)
        assert config.shift_downshift_brake_display_min == pytest.approx(0.10)
        assert config.shift_downshift_throttle_display_max == pytest.approx(0.30)

    def test_shift_v2_env_overrides(self):
        """All FH6_SHIFT_* v2 env vars set -> overrides apply."""
        overrides = {
            "FH6_SHIFT_PRIOR_REBUILD_COOLDOWN_S": "600",
            "FH6_SHIFT_PRIOR_MIN_FP_SAMPLES": "2000",
            "FH6_SHIFT_TCS_SLIP_THRESHOLD": "0.75",
            "FH6_SHIFT_TCS_TORQUE_FLOOR_RATIO": "0.90",
            "FH6_SHIFT_ASSIST_ALERT_PCT": "0.10",
            "FH6_SHIFT_ASSIST_RECENT_WINDOW": "1800",
            "FH6_SHIFT_TRANS_MODE_RING_CAP": "60",
            "FH6_SHIFT_TRANS_MODE_MIN_SAMPLES": "20",
            "FH6_SHIFT_TRANS_MODE_AUTO_STDEV_RPM": "100.0",
            "FH6_SHIFT_DOWNSHIFT_BRAKE_DISPLAY_MIN": "0.20",
            "FH6_SHIFT_DOWNSHIFT_THROTTLE_DISPLAY_MAX": "0.50",
        }

        with patch.dict(os.environ, overrides, clear=False):
            config = load_from_env()

        assert config.shift_prior_rebuild_cooldown_s == 600
        assert config.shift_prior_min_fp_samples == 2000
        assert config.shift_tcs_slip_threshold == pytest.approx(0.75)
        assert config.shift_tcs_torque_floor_ratio == pytest.approx(0.90)
        assert config.shift_assist_alert_pct == pytest.approx(0.10)
        assert config.shift_assist_recent_window == 1800
        assert config.shift_trans_mode_ring_cap == 60
        assert config.shift_trans_mode_min_samples == 20
        assert config.shift_trans_mode_auto_stdev_rpm == pytest.approx(100.0)
        assert config.shift_downshift_brake_display_min == pytest.approx(0.20)
        assert config.shift_downshift_throttle_display_max == pytest.approx(0.50)


def test_validate_rejects_inverted_slip_thresholds() -> None:
    """shift_tcs_slip_threshold <= shift_combined_slip_max -> construction raises.

    pydantic-settings runs `_check_invariants` during construction, so the
    failure surface is `AppConfig(...)` itself rather than a separate
    `.validate()` call.
    """
    with pytest.raises(ValueError, match="shift_tcs_slip_threshold"):
        AppConfig(shift_tcs_slip_threshold=0.10)  # below default combined=0.20
