"""Tests for the shift training frame filter (FR-003)."""

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


def _default_ai() -> AssistCheckInputs:
    """Default AssistCheckInputs for v1 tests: Signal B disabled (no class prior)."""
    return AssistCheckInputs(
        class_prior_q90=None,
        tcs_slip_threshold=0.50,
        tcs_torque_floor_ratio=0.85,
    )


def build_frame_raw(
    is_race_on: bool = True,
    inputs: dict | None = None,
    drivetrain: dict | None = None,
    wheels: dict | None = None,
) -> FrameRaw:
    """Helper to construct a minimal FrameRaw with defaults for testing."""
    if inputs is None:
        inputs = {
            "throttle": 0.99,
            "brake": 0.0,
            "clutch": 0.0,
            "steer": 0.05,
        }
    if drivetrain is None:
        drivetrain = {
            "clutch": 0.0,
            "gear": 3,
        }
    if wheels is None:
        wheels = {
            "fl": {"combinedSlip": 0.1},
            "fr": {"combinedSlip": 0.1},
            "rl": {"combinedSlip": 0.1},
            "rr": {"combinedSlip": 0.1},
        }

    return FrameRaw(
        is_race_on=is_race_on,
        timestamp_ms=0,
        engine={},
        drivetrain=drivetrain,
        motion={},
        inputs=inputs,
        wheels=wheels,
        world={},
        race={},
        tail_reserved_byte=0,
    )


def build_decoded_frame(frame_raw: FrameRaw | None = None) -> DecodedFrame:
    """Helper to construct a DecodedFrame with defaults."""
    if frame_raw is None:
        frame_raw = build_frame_raw()

    return DecodedFrame(
        session_id=SessionId("test-session"),
        car_id=CarId("test-car"),
        received_at=datetime.now(),
        raw=frame_raw,
    )


def build_filter_inputs(
    config: AppConfig | None = None,
    is_drift_session: bool = False,
    session_uptime_s: float = 120.0,
    recent_gears: list[int] | None = None,
    recent_boost_psi: list[float] | None = None,
    is_turbo: bool = True,
) -> FilterInputs:
    """Helper to construct FilterInputs with defaults."""
    if config is None:
        config = AppConfig(
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
    if recent_gears is None:
        recent_gears = [3, 3, 3, 3, 3, 3]
    if recent_boost_psi is None:
        # Settled: max change ~0.03 psi per frame at 30Hz = ~1.0 psi/s
        recent_boost_psi = [12.0, 12.01, 12.01, 12.00, 12.01]

    return FilterInputs(
        config=config,
        is_drift_session=is_drift_session,
        session_uptime_s=session_uptime_s,
        recent_gears=recent_gears,
        recent_boost_psi=recent_boost_psi,
        is_turbo=is_turbo,
    )


class TestCheckFrame:
    """Tests for the check_frame eligibility filter."""

    def test_happy_path_all_conditions_pass(self):
        """All conditions pass -> eligible=True, reason=None."""
        frame = build_decoded_frame()
        fi = build_filter_inputs()

        verdict = check_frame(frame, fi, _default_ai())

        assert verdict.eligible is True
        assert verdict.reason is None
        assert verdict.boost_settled is True

    def test_not_racing_fails(self):
        """is_race_on=False -> eligible=False, reason='not_racing'."""
        frame = build_decoded_frame(build_frame_raw(is_race_on=False))
        fi = build_filter_inputs()

        verdict = check_frame(frame, fi, _default_ai())

        assert verdict.eligible is False
        assert verdict.reason == "not_racing"

    def test_drift_session_fails(self):
        """is_drift_session=True -> eligible=False, reason='drift'."""
        frame = build_decoded_frame()
        fi = build_filter_inputs(is_drift_session=True)

        verdict = check_frame(frame, fi, _default_ai())

        assert verdict.eligible is False
        assert verdict.reason == "drift"

    def test_warmup_timeout_fails(self):
        """session_uptime_s < warmup_seconds -> eligible=False, reason='warmup'."""
        frame = build_decoded_frame()
        fi = build_filter_inputs(session_uptime_s=30.0)

        verdict = check_frame(frame, fi, _default_ai())

        assert verdict.eligible is False
        assert verdict.reason == "warmup"

    def test_throttle_minimum_fails(self):
        """throttle < shift_throttle_min -> eligible=False, reason='throttle'."""
        frame = build_decoded_frame(
            build_frame_raw(inputs={"throttle": 0.90, "brake": 0.0, "clutch": 0.0, "steer": 0.05})
        )
        fi = build_filter_inputs()

        verdict = check_frame(frame, fi, _default_ai())

        assert verdict.eligible is False
        assert verdict.reason == "throttle"

    def test_brake_maximum_fails(self):
        """brake >= shift_brake_max -> eligible=False, reason='brake'."""
        frame = build_decoded_frame(
            build_frame_raw(inputs={"throttle": 0.99, "brake": 0.06, "clutch": 0.0, "steer": 0.05})
        )
        fi = build_filter_inputs()

        verdict = check_frame(frame, fi, _default_ai())

        assert verdict.eligible is False
        assert verdict.reason == "brake"

    def test_input_clutch_too_high_fails(self):
        """inputs.clutch >= 0.5 -> eligible=False, reason='input_clutch'."""
        frame = build_decoded_frame(
            build_frame_raw(inputs={"throttle": 0.99, "brake": 0.0, "clutch": 0.5, "steer": 0.05})
        )
        fi = build_filter_inputs()

        verdict = check_frame(frame, fi, _default_ai())

        assert verdict.eligible is False
        assert verdict.reason == "input_clutch"

    def test_drive_clutch_too_high_fails(self):
        """drivetrain.clutch >= 0.5 -> eligible=False, reason='drive_clutch'."""
        frame = build_decoded_frame(build_frame_raw(drivetrain={"clutch": 0.5, "gear": 3}))
        fi = build_filter_inputs()

        verdict = check_frame(frame, fi, _default_ai())

        assert verdict.eligible is False
        assert verdict.reason == "drive_clutch"

    def test_steer_magnitude_too_high_fails(self):
        """abs(steer) >= shift_steer_max -> eligible=False, reason='steer'."""
        frame = build_decoded_frame(
            build_frame_raw(inputs={"throttle": 0.99, "brake": 0.0, "clutch": 0.0, "steer": 0.10})
        )
        fi = build_filter_inputs()

        verdict = check_frame(frame, fi, _default_ai())

        assert verdict.eligible is False
        assert verdict.reason == "steer"

    def test_gear_zero_or_negative_fails(self):
        """gear <= 0 -> eligible=False, reason='gear'."""
        frame = build_decoded_frame(build_frame_raw(drivetrain={"clutch": 0.0, "gear": 0}))
        fi = build_filter_inputs()

        verdict = check_frame(frame, fi, _default_ai())

        assert verdict.eligible is False
        assert verdict.reason == "gear"

    def test_gear_unstable_fails(self):
        """Recent gears not all equal to current gear -> eligible=False, reason='gear_unstable'."""
        frame = build_decoded_frame(build_frame_raw(drivetrain={"clutch": 0.0, "gear": 3}))
        # recent_gears: [3, 2, 3, 3, 3, 3] — last 5 are [2, 3, 3, 3, 3], not all 3
        fi = build_filter_inputs(recent_gears=[3, 2, 3, 3, 3, 3])

        verdict = check_frame(frame, fi, _default_ai())

        assert verdict.eligible is False
        assert verdict.reason == "gear_unstable"

    def test_slip_too_high_fails(self):
        """Any wheel combinedSlip >= shift_combined_slip_max -> eligible=False, reason='slip'."""
        frame = build_decoded_frame(
            build_frame_raw(
                wheels={
                    "fl": {"combinedSlip": 0.25},
                    "fr": {"combinedSlip": 0.1},
                    "rl": {"combinedSlip": 0.1},
                    "rr": {"combinedSlip": 0.1},
                }
            )
        )
        fi = build_filter_inputs()

        verdict = check_frame(frame, fi, _default_ai())

        assert verdict.eligible is False
        assert verdict.reason == "slip"

    def test_boost_unsettled_fails_for_turbo_car(self):
        """Boost not settled (turbo car only) -> eligible=False, reason='boost_unsettled'."""
        frame = build_decoded_frame()
        # recent_boost_psi: [10.0, 15.0, 12.0, 12.0, 12.0] — large swings
        fi = build_filter_inputs(recent_boost_psi=[10.0, 15.0, 12.0, 12.0, 12.0], is_turbo=True)

        verdict = check_frame(frame, fi, _default_ai())

        assert verdict.eligible is False
        assert verdict.reason == "boost_unsettled"

    def test_short_circuit_first_failure_wins(self):
        """When multiple conditions fail, first one in order wins."""
        frame = build_decoded_frame(build_frame_raw(is_race_on=False))
        fi = build_filter_inputs(is_drift_session=True, session_uptime_s=30.0)

        verdict = check_frame(frame, fi, _default_ai())

        # not_racing is checked first, so it should be the reason
        assert verdict.eligible is False
        assert verdict.reason == "not_racing"

    def test_boost_settled_true_for_na_cars_regardless_of_boost(self):
        """For NA cars (is_turbo=False), boost_settled=True regardless of recent_boost_psi."""
        frame = build_decoded_frame()
        # Deliberately use wildly unstable boost values
        fi = build_filter_inputs(recent_boost_psi=[0.0, 100.0, 0.0, 100.0, 0.0], is_turbo=False)

        verdict = check_frame(frame, fi, _default_ai())

        # Should be eligible (passes all other checks) and boost_settled should be True
        assert verdict.eligible is True
        assert verdict.boost_settled is True

    def test_boost_settled_flag_reflects_calculation_even_when_ineligible(self):
        """boost_settled flag is set based on calculation, even if verdict is ineligible."""
        frame = build_decoded_frame(build_frame_raw(is_race_on=False))
        # Settled boost: small changes
        fi = build_filter_inputs(recent_boost_psi=[12.0, 12.01, 12.01, 12.00, 12.01], is_turbo=True)

        verdict = check_frame(frame, fi, _default_ai())

        assert verdict.eligible is False
        assert verdict.reason == "not_racing"
        assert verdict.boost_settled is True

    def test_steer_negative_magnitude_checked(self):
        """Negative steer values are checked by absolute value."""
        frame = build_decoded_frame(
            build_frame_raw(inputs={"throttle": 0.99, "brake": 0.0, "clutch": 0.0, "steer": -0.12})
        )
        fi = build_filter_inputs()

        verdict = check_frame(frame, fi, _default_ai())

        assert verdict.eligible is False
        assert verdict.reason == "steer"

    def test_warmup_passes_at_threshold(self):
        """session_uptime_s == warmup_seconds passes."""
        frame = build_decoded_frame()
        fi = build_filter_inputs(session_uptime_s=60.0)

        verdict = check_frame(frame, fi, _default_ai())

        assert verdict.eligible is True
        assert verdict.reason is None

    def test_throttle_passes_at_minimum(self):
        """throttle == shift_throttle_min passes."""
        frame = build_decoded_frame(
            build_frame_raw(inputs={"throttle": 0.95, "brake": 0.0, "clutch": 0.0, "steer": 0.05})
        )
        fi = build_filter_inputs()

        verdict = check_frame(frame, fi, _default_ai())

        assert verdict.eligible is True
        assert verdict.reason is None
