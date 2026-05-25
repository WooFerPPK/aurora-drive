"""Pure-function frame filter for engine-curve training eligibility (FR-003).

No I/O, no state — all state is passed via arguments. Returns a verdict with
a stable string reason on rejection.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from fh6.domain.entities.frame import DecodedFrame
from fh6.infrastructure.config import AppConfig


@dataclass(frozen=True, slots=True)
class FilterInputs:
    """Input parameters for the training filter.

    Attributes:
        config: Runtime configuration (thresholds, limits).
        is_drift_session: True if drift-mode session.
        session_uptime_s: Seconds elapsed since session start.
        recent_gears: Sequence of recent gear values, most-recent-last.
        recent_boost_psi: Sequence of recent boost PSI values, most-recent-last (~5 samples).
        is_turbo: True if vehicle has turbocharger.
    """

    config: AppConfig
    is_drift_session: bool
    session_uptime_s: float
    recent_gears: Sequence[int]
    recent_boost_psi: Sequence[float]
    is_turbo: bool


@dataclass(frozen=True, slots=True)
class AssistCheckInputs:
    """Optional second-arg block carrying class-prior context.

    When `class_prior_q90` is None, Signal B is skipped (only Signal A active).
    """

    class_prior_q90: float | None
    tcs_slip_threshold: float
    tcs_torque_floor_ratio: float


@dataclass(frozen=True, slots=True)
class EligibilityVerdict:
    """Result of frame eligibility check.

    Attributes:
        eligible: True if frame is eligible for training.
        reason: Reason code if ineligible (e.g., "not_racing", "warmup"). None if eligible.
        boost_settled: True if boost is settled (or car is NA). Reported regardless of overall verdict.
        intervention_suspected: True when the reject reason is a TCS/STM intervention signal
            (FR-037 Signal A or FR-038 Signal B). False otherwise.
    """

    eligible: bool
    reason: str | None
    boost_settled: bool
    intervention_suspected: bool = False


def _compute_boost_settled(fi: FilterInputs) -> bool:
    """Compute whether boost is settled.

    For NA cars (not turbo), always True.
    For turbo cars, check if max rate of change over recent_boost_psi is within limit.
    Assumes 30Hz frame spacing (~33.3 ms per frame, ~0.0333 s).
    """
    if not fi.is_turbo:
        return True

    if len(fi.recent_boost_psi) < 2:
        return False

    # Compute max absolute change between consecutive samples.
    max_change = 0.0
    for i in range(1, len(fi.recent_boost_psi)):
        change = abs(fi.recent_boost_psi[i] - fi.recent_boost_psi[i - 1])
        max_change = max(max_change, change)

    # 30Hz = ~0.033 s per frame. Max rate in psi/s.
    frame_interval_s = 1.0 / 30.0
    max_rate_psi_per_s = max_change / frame_interval_s

    return max_rate_psi_per_s <= fi.config.shift_boost_settle_psi_per_s


def check_frame(frame: DecodedFrame, fi: FilterInputs, ai: AssistCheckInputs) -> EligibilityVerdict:
    """Check if a frame is eligible for engine-curve training.

    Checks conditions in order; returns on first failure.

    Args:
        frame: Decoded telemetry frame.
        fi: Filter inputs (config, session state, recent history).
        ai: Assist-check inputs (class-prior q90 + TCS thresholds, FR-037/FR-038).

    Returns:
        EligibilityVerdict with eligible flag, reason (if ineligible), and boost_settled state.
    """
    cfg = fi.config

    # Compute boost settled once; used for gating and returned in verdict.
    boost_settled = _compute_boost_settled(fi)

    # 1. Must be racing.
    if not frame.raw.is_race_on:
        return EligibilityVerdict(
            eligible=False,
            reason="not_racing",
            boost_settled=boost_settled,
        )

    # 2. Not a drift session.
    if fi.is_drift_session:
        return EligibilityVerdict(
            eligible=False,
            reason="drift",
            boost_settled=boost_settled,
        )

    # 3. Session must be past warmup.
    if fi.session_uptime_s < cfg.shift_warmup_seconds:
        return EligibilityVerdict(
            eligible=False,
            reason="warmup",
            boost_settled=boost_settled,
        )

    # 4. Throttle minimum.
    throttle = frame.raw.inputs.get("throttle", 0.0)
    if throttle < cfg.shift_throttle_min:
        return EligibilityVerdict(
            eligible=False,
            reason="throttle",
            boost_settled=boost_settled,
        )

    # 5. Brake maximum.
    brake = frame.raw.inputs.get("brake", 0.0)
    if brake >= cfg.shift_brake_max:
        return EligibilityVerdict(
            eligible=False,
            reason="brake",
            boost_settled=boost_settled,
        )

    # 6. Input clutch < 0.5 (hardcoded).
    input_clutch = frame.raw.inputs.get("clutch", 0.0)
    if input_clutch >= 0.5:
        return EligibilityVerdict(
            eligible=False,
            reason="input_clutch",
            boost_settled=boost_settled,
        )

    # 7. Drivetrain clutch < 0.5 (hardcoded).
    drive_clutch = frame.raw.drivetrain.get("clutch", 0.0)
    if drive_clutch >= 0.5:
        return EligibilityVerdict(
            eligible=False,
            reason="drive_clutch",
            boost_settled=boost_settled,
        )

    # 8. Steer magnitude < shift_steer_max.
    steer = frame.raw.inputs.get("steer", 0.0)
    if abs(steer) >= cfg.shift_steer_max:
        return EligibilityVerdict(
            eligible=False,
            reason="steer",
            boost_settled=boost_settled,
        )

    # 9. Current gear must be positive.
    current_gear = frame.raw.drivetrain.get("gear", 0)
    if current_gear <= 0:
        return EligibilityVerdict(
            eligible=False,
            reason="gear",
            boost_settled=boost_settled,
        )

    # 10. Recent gears must be stable (all equal to current gear).
    if len(fi.recent_gears) > 0:
        # Check last cfg.shift_gear_stable_frames gears.
        stable_count = cfg.shift_gear_stable_frames
        gears_to_check = list(fi.recent_gears[-stable_count:])
        if not all(g == current_gear for g in gears_to_check):
            return EligibilityVerdict(
                eligible=False,
                reason="gear_unstable",
                boost_settled=boost_settled,
            )

    # 11. Slip check (FR-003 clause 11 + FR-037 Signal A).
    wheels = frame.raw.wheels
    for wheel_key in ["fl", "fr", "rl", "rr"]:
        wheel_data = wheels.get(wheel_key, {})
        slip = wheel_data.get("combinedSlip", 0.0)
        if slip >= ai.tcs_slip_threshold:
            return EligibilityVerdict(
                eligible=False,
                reason="assist_intervention",
                boost_settled=boost_settled,
                intervention_suspected=True,
            )
        if slip >= cfg.shift_combined_slip_max:
            return EligibilityVerdict(
                eligible=False,
                reason="slip",
                boost_settled=boost_settled,
                intervention_suspected=False,
            )

    # 11.5 — TCS Signal B (FR-038): torque deficit against class-prior ceiling.
    if ai.class_prior_q90 is not None:
        observed = frame.raw.engine.get("torque_nm", 0.0)
        if observed < ai.tcs_torque_floor_ratio * ai.class_prior_q90:
            return EligibilityVerdict(
                eligible=False,
                reason="assist_intervention",
                boost_settled=boost_settled,
                intervention_suspected=True,
            )

    # 12. Boost must be settled (turbo only; gated on is_turbo).
    if fi.is_turbo and not boost_settled:
        return EligibilityVerdict(
            eligible=False,
            reason="boost_unsettled",
            boost_settled=boost_settled,
        )

    # All checks pass.
    return EligibilityVerdict(
        eligible=True,
        reason=None,
        boost_settled=boost_settled,
    )
