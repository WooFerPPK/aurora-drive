"""Tests for the v2 assist-intervention clause in the shift training filter.

Covers FR-037 (Signal A: TCS slip threshold) and FR-038 (Signal B: torque
deficit vs class-prior q90).
"""

from __future__ import annotations

from datetime import datetime

from fh6.application.services.shift.training_filter import (
    AssistCheckInputs,
    FilterInputs,
    check_frame,
)
from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.infrastructure.config import AppConfig


def _build_config() -> AppConfig:
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
        rewind_yaw_tolerance_rad=1.5708,
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


def _build_frame(
    *,
    throttle: float = 1.0,
    combined_slip: float = 0.0,
    torque_nm: float = 0.0,
) -> DecodedFrame:
    raw = FrameRaw(
        is_race_on=True,
        timestamp_ms=0,
        engine={"torque_nm": torque_nm},
        drivetrain={"clutch": 0.0, "gear": 3},
        motion={},
        inputs={"throttle": throttle, "brake": 0.0, "clutch": 0.0, "steer": 0.05},
        wheels={
            "fl": {"combinedSlip": combined_slip},
            "fr": {"combinedSlip": combined_slip},
            "rl": {"combinedSlip": combined_slip},
            "rr": {"combinedSlip": combined_slip},
        },
        world={},
        race={},
        tail_reserved_byte=0,
    )
    return DecodedFrame(
        session_id=SessionId("test-session"),
        car_id=CarId("test-car"),
        received_at=datetime.now(),
        raw=raw,
    )


def _build_fi(config: AppConfig) -> FilterInputs:
    return FilterInputs(
        config=config,
        is_drift_session=False,
        session_uptime_s=120.0,
        recent_gears=[3, 3, 3, 3, 3, 3],
        recent_boost_psi=[12.0, 12.01, 12.01, 12.00, 12.01],
        is_turbo=True,
    )


def _build_ai(
    *,
    cfg: AppConfig,
    class_prior_q90: float | None = None,
) -> AssistCheckInputs:
    return AssistCheckInputs(
        class_prior_q90=class_prior_q90,
        tcs_slip_threshold=cfg.shift_tcs_slip_threshold,
        tcs_torque_floor_ratio=cfg.shift_tcs_torque_floor_ratio,
    )


class TestAssistDetection:
    """Tests for FR-037 (Signal A) and FR-038 (Signal B)."""

    def test_signal_a_slip_above_tcs_threshold_flags_assist_intervention(self) -> None:
        """Combined slip 0.6 (> 0.50 TCS threshold) -> assist_intervention."""
        cfg = _build_config()
        frame = _build_frame(throttle=1.0, combined_slip=0.6)
        fi = _build_fi(cfg)
        ai = _build_ai(cfg=cfg)

        verdict = check_frame(frame, fi, ai)

        assert verdict.eligible is False
        assert verdict.reason == "assist_intervention"
        assert verdict.intervention_suspected is True

    def test_v1_slip_band_still_returns_slip_reason(self) -> None:
        """Combined slip 0.3 (above v1 0.20, below v2 0.50) -> 'slip' (v1 preserved)."""
        cfg = _build_config()
        frame = _build_frame(throttle=1.0, combined_slip=0.3)
        fi = _build_fi(cfg)
        ai = _build_ai(cfg=cfg)

        verdict = check_frame(frame, fi, ai)

        assert verdict.eligible is False
        assert verdict.reason == "slip"
        assert verdict.intervention_suspected is False

    def test_signal_b_torque_deficit_flags_assist_intervention(self) -> None:
        """Torque 300 with class-prior q90 500 (ratio 0.6 < 0.85) -> assist_intervention."""
        cfg = _build_config()
        frame = _build_frame(throttle=1.0, combined_slip=0.05, torque_nm=300.0)
        fi = _build_fi(cfg)
        ai = _build_ai(cfg=cfg, class_prior_q90=500.0)

        verdict = check_frame(frame, fi, ai)

        assert verdict.eligible is False
        assert verdict.reason == "assist_intervention"
        assert verdict.intervention_suspected is True

    def test_signal_b_inactive_without_class_prior(self) -> None:
        """Torque deficit but class_prior_q90=None -> eligible (Signal B skipped)."""
        cfg = _build_config()
        frame = _build_frame(throttle=1.0, combined_slip=0.05, torque_nm=300.0)
        fi = _build_fi(cfg)
        ai = _build_ai(cfg=cfg, class_prior_q90=None)

        verdict = check_frame(frame, fi, ai)

        assert verdict.eligible is True
        assert verdict.reason is None
        assert verdict.intervention_suspected is False

    def test_signal_b_passes_when_torque_above_floor(self) -> None:
        """Torque 480 with class-prior q90 500 (ratio 0.96 >= 0.85) -> eligible."""
        cfg = _build_config()
        frame = _build_frame(throttle=1.0, combined_slip=0.05, torque_nm=480.0)
        fi = _build_fi(cfg)
        ai = _build_ai(cfg=cfg, class_prior_q90=500.0)

        verdict = check_frame(frame, fi, ai)

        assert verdict.eligible is True
        assert verdict.reason is None
        assert verdict.intervention_suspected is False
