"""ShiftEventEvaluator — evaluates gear-change events and persists clean shifts.

Implements the ShiftEventListener Protocol defined in shift_predictor.py (FR-015
to FR-017). FR-048 extends the evaluator to also handle downshifts via a
parallel rev-match-residual path (no propulsive-torque model on closed throttle).

# FR-017: this module writes ONLY to shift_events_clean. Never upsert engine_curves bins.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime

from fh6.application.services.shift.curve_resolver import ShiftCurveResolver
from fh6.domain.entities.frame import DecodedFrame
from fh6.domain.ports.shift_predictor_repo import (
    BinRecord,
    RatioRecord,
    ShiftEventRow,
    ShiftPredictorRepository,
)
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint
from fh6.domain.value_objects.ids import SessionId
from fh6.infrastructure.config import AppConfig

# FR-048: rev-match dead-band (RPM) — actual post-shift RPM within ±this of
# the rev-match target costs zero. Outside the band: linear penalty scaled by
# _DOWNSHIFT_COST_PER_RPM.
_DOWNSHIFT_REV_MATCH_BAND_RPM = 300.0
# FR-048: seconds-per-RPM penalty applied to (|delta_rpm| - 300) over 1000.
# Deliberately conservative (spec test asserts presence, not calibration).
_DOWNSHIFT_COST_PER_RPM = 0.05 / 1000.0
# FR-048 clean-downshift gate: closed-throttle threshold. A frame with
# brake >= shift_downshift_brake_display_min OR throttle < this counts as
# "in a downshift context".
_DOWNSHIFT_CLEAN_THROTTLE_MAX = 0.30


# ---------------------------------------------------------------------------
# Class-based mass fallback (kg). FH6 doesn't ship car mass on the wire.
# These are rough averages by performance class; good enough for residual
# estimation. Refine in v2 if/when a mass source is available.
# ---------------------------------------------------------------------------

CLASS_MASS_KG: dict[str, int] = {
    "D": 1100,
    "C": 1250,
    "B": 1400,
    "A": 1500,
    "S": 1500,
    "R": 1500,
    "P": 1500,
    "X": 1500,
}

_MASS_FALLBACK_KG = 1500

# Minimum frames required in each window for a shift to be evaluated.
_MIN_WINDOW_FRAMES = 5

# Turbo boost stability threshold: if boost changes faster than this (psi/s)
# across the post-window, the shift is rejected as not yet settled.
_TURBO_SETTLE_PSI_PER_S = 1.0

# Minimum road speed (m/s) needed to compute accel-along-motion without
# noise-floor / div-by-zero issues.
_MIN_SPEED_MPS = 1.0

# Est-cost cap (seconds) — v1 heuristic, not a physical model.
_EST_COST_CAP_S = 0.20


class ShiftEventEvaluator:
    """Evaluates gear-change events and persists clean-shift rows.

    Called by ShiftPredictor (via the ShiftEventListener Protocol) each time
    a gear change is detected.  Determines whether the shift was "clean" per
    FR-015 criteria, computes a wheel-torque residual, and persists the result
    to shift_events_clean via the repository.

    FR-017 guarantee: this class NEVER calls repo.upsert_bin.
    """

    def __init__(
        self,
        *,
        config: AppConfig,
        repo: ShiftPredictorRepository,
        curve_resolver: ShiftCurveResolver,
    ) -> None:
        self._cfg = config
        self._repo = repo
        self._resolver = curve_resolver

    # ------------------------------------------------------------------
    # Public: ShiftEventListener protocol
    # ------------------------------------------------------------------

    async def on_shift(
        self,
        session_id: SessionId,
        gear_from: int,
        gear_to: int,
        at: datetime,
        pre_window: Sequence[DecodedFrame],
        post_window: Sequence[DecodedFrame],
        *,
        fingerprint: EngineFingerprint,
        bins_snapshot: dict[tuple[int, int], BinRecord],
        ratios_snapshot: dict[int, RatioRecord],
        recommended_rpm: float | None,
        recommendation_conf: float | None,
    ) -> None:
        """Called by ShiftPredictor on each gear change.

        May write one ShiftEventRow if the shift was clean; otherwise no-op.

        Parameters
        ----------
        session_id:
            The active session identifier.
        gear_from, gear_to:
            Gear numbers involved in the shift.
        at:
            UTC timestamp of the shift detection.
        pre_window:
            Frames captured before the shift (from the ring buffer).
        post_window:
            Frames captured after the shift (post-settling window).
        fingerprint:
            Engine fingerprint required for the shift_events_clean PK.
        bins_snapshot:
            Trainer's current snapshot dict[(gear, rpm_bin), BinRecord].
            Read-only — never mutated.
        ratios_snapshot:
            Kalman's current snapshot dict[gear, RatioRecord].
            Read-only — never mutated.
        recommended_rpm:
            The predictor's live shift recommendation at the moment of shift.
            For an upshift this is the pre-shift target RPM the driver should
            have shifted at. For a downshift (FR-048) it is the predictor's
            downshift pre-shift target (``current_gear_downshift_target``).
        recommendation_conf:
            Confidence of the recommendation (0–1).
        """
        # --- Step 1: Validate window sizes ---
        if len(pre_window) < _MIN_WINDOW_FRAMES or len(post_window) < _MIN_WINDOW_FRAMES:
            return

        # --- Direction dispatch (FR-048) ---
        # gear_to > gear_from: classic upshift → wheel-torque residual path.
        # gear_to < gear_from: downshift → rev-match residual path.
        # gear_to == gear_from: shouldn't happen — defensive no-op.
        if gear_to < gear_from:
            await self._handle_downshift(
                session_id=session_id,
                gear_from=gear_from,
                gear_to=gear_to,
                at=at,
                pre_window=pre_window,
                post_window=post_window,
                fingerprint=fingerprint,
                ratios_snapshot=ratios_snapshot,
                recommended_rpm=recommended_rpm,
                recommendation_conf=recommendation_conf,
            )
            return
        if gear_to == gear_from:
            return

        # --- Upshift path (legacy v1, FR-015) ---
        await self._handle_upshift(
            session_id=session_id,
            gear_from=gear_from,
            gear_to=gear_to,
            at=at,
            pre_window=pre_window,
            post_window=post_window,
            fingerprint=fingerprint,
            bins_snapshot=bins_snapshot,
            ratios_snapshot=ratios_snapshot,
            recommended_rpm=recommended_rpm,
            recommendation_conf=recommendation_conf,
        )

    # ------------------------------------------------------------------
    # Upshift (v1, FR-015)
    # ------------------------------------------------------------------

    async def _handle_upshift(
        self,
        *,
        session_id: SessionId,
        gear_from: int,
        gear_to: int,
        at: datetime,
        pre_window: Sequence[DecodedFrame],
        post_window: Sequence[DecodedFrame],
        fingerprint: EngineFingerprint,
        bins_snapshot: dict[tuple[int, int], BinRecord],
        ratios_snapshot: dict[int, RatioRecord],
        recommended_rpm: float | None,
        recommendation_conf: float | None,
    ) -> None:
        """v1 upshift evaluator: wheel-torque residual + est_cost (FR-015)."""
        # --- Step 2: Check clean-shift input criteria over both windows ---
        all_frames = list(pre_window) + list(post_window)
        for frame in all_frames:
            inp = frame.raw.inputs
            if inp.get("throttle", 0.0) < self._cfg.shift_throttle_min:
                return
            if inp.get("brake", 0.0) >= self._cfg.shift_brake_max:
                return
            if abs(inp.get("steer", 0.0)) >= self._cfg.shift_steer_max:
                return
            wheels = frame.raw.wheels
            for corner in ("fl", "fr", "rl", "rr"):
                slip = (wheels.get(corner) or {}).get("combinedSlip", 0.0)
                if slip >= self._cfg.shift_combined_slip_max:
                    return

        # --- Step 3: Turbo settling check (post window only) ---
        # Detect turbo: any frame in post_window with boost_psi > 1.0
        post_boosts = [
            float(f.raw.engine.get("boost_psi", f.raw.engine.get("boost", 0.0)))
            for f in post_window
        ]
        is_turbo = any(b > 1.0 for b in post_boosts)
        if is_turbo:
            # Compute rate-of-change of boost across post_window.
            # Approximate window duration from received_at timestamps.
            t_first = post_window[0].received_at
            t_last = post_window[-1].received_at
            duration_s = (t_last - t_first).total_seconds()
            if duration_s > 0.0:
                boost_delta = abs(post_boosts[-1] - post_boosts[0])
                boost_rate = boost_delta / duration_s
                if boost_rate >= _TURBO_SETTLE_PSI_PER_S:
                    return  # boost still settling — not a clean shift

        # --- Step 4: Pre-shift RPM (last frame before the shift) ---
        actual_rpm = float(
            pre_window[-1].raw.engine.get("currentRpm", pre_window[-1].raw.engine.get("rpm", 0.0))
        )

        # --- Step 5: Post-shift mean RPM ---
        post_rpms = [
            float(f.raw.engine.get("currentRpm", f.raw.engine.get("rpm", 0.0))) for f in post_window
        ]
        post_rpm_mean = sum(post_rpms) / len(post_rpms)

        # --- Step 6: Mass lookup ---
        sample_frame = post_window[0]
        car_class = sample_frame.raw.world.get("carClass")
        mass_kg = (
            CLASS_MASS_KG.get(car_class, _MASS_FALLBACK_KG) if car_class else _MASS_FALLBACK_KG
        )

        # --- Step 7: Measured wheel torque via accel-along-motion ---
        accel_values: list[float] = []
        for frame in post_window:
            motion = frame.raw.motion
            v = motion.get("velocity") or motion.get("velocityVec")
            a = motion.get("acceleration") or motion.get("accelerationVec")
            if v is None or a is None:
                # Fall back to scalar speed + accel if available
                speed_scalar = float(motion.get("speed", 0.0))
                accel_scalar = float(motion.get("accel", motion.get("accelerationLong", 0.0)))
                if speed_scalar < _MIN_SPEED_MPS:
                    return  # too slow — skip the whole shift
                accel_values.append(accel_scalar)
                continue

            # v and a may be dicts or lists/tuples
            if isinstance(v, dict):
                vx, vy, vz = float(v.get("x", 0.0)), float(v.get("y", 0.0)), float(v.get("z", 0.0))
            else:
                vx, vy, vz = float(v[0]), float(v[1]), float(v[2])

            if isinstance(a, dict):
                ax, ay, az = float(a.get("x", 0.0)), float(a.get("y", 0.0)), float(a.get("z", 0.0))
            else:
                ax, ay, az = float(a[0]), float(a[1]), float(a[2])

            speed = math.sqrt(vx * vx + vy * vy + vz * vz)
            if speed < _MIN_SPEED_MPS:
                return  # too slow — skip the whole shift

            # accel along motion: (v · a) / |v|
            dot = vx * ax + vy * ay + vz * az
            accel_along = dot / speed
            accel_values.append(accel_along)

        if not accel_values:
            return

        mean_accel = sum(accel_values) / len(accel_values)
        measured_torque = mass_kg * mean_accel

        # --- Step 8: Predicted wheel torque from curve resolver ---
        # Group bins for gear_to
        bins_for_gear_to = [rec for (g, _rpm_bin), rec in bins_snapshot.items() if g == gear_to]

        # Look up idle/max RPM from the post-window frames
        idle_rpm = float(
            post_window[0].raw.engine.get(
                "idleRpm", post_window[0].raw.engine.get("idle_rpm", 900.0)
            )
        )
        max_rpm = float(
            post_window[0].raw.engine.get(
                "maxRpm", post_window[0].raw.engine.get("max_rpm", 8000.0)
            )
        )

        predicted_torque: float | None = None
        est_cost_s: float | None = None

        if bins_for_gear_to and gear_to in ratios_snapshot:
            curve_fit = self._resolver.fit_curve(bins_for_gear_to, idle_rpm, max_rpm)
            if curve_fit is not None:
                ratio = ratios_snapshot[gear_to].ratio
                predicted_torque = curve_fit.evaluate(post_rpm_mean) * ratio

                # --- Step 9: Estimate shift cost (v1 heuristic) ---
                # Normalised torque deficit times a calibration constant (0.05 s/unit).
                # Capped at _EST_COST_CAP_S (0.20 s) to keep the estimate bounded.
                # TODO(v2): replace with a proper physics-based model.
                if predicted_torque > 0.0:
                    deficit_fraction = max(
                        0.0, (predicted_torque - measured_torque) / predicted_torque
                    )
                    est_cost_s = min(_EST_COST_CAP_S, deficit_fraction * 0.05)

        # --- Step 10: Build and persist the ShiftEventRow ---
        row = ShiftEventRow(
            id=None,
            session_id=session_id,
            fingerprint=fingerprint,
            shift_at=at,
            gear_from=gear_from,
            gear_to=gear_to,
            actual_rpm=actual_rpm,
            recommended_rpm=recommended_rpm,
            recommendation_conf=recommendation_conf,
            predicted_post_torque=predicted_torque,
            measured_post_torque=measured_torque,
            est_cost_s=est_cost_s,
        )
        await self._repo.record_shift_event(row)

    # ------------------------------------------------------------------
    # Downshift (FR-048): rev-match residual
    # ------------------------------------------------------------------

    async def _handle_downshift(
        self,
        *,
        session_id: SessionId,
        gear_from: int,
        gear_to: int,
        at: datetime,
        pre_window: Sequence[DecodedFrame],
        post_window: Sequence[DecodedFrame],
        fingerprint: EngineFingerprint,
        ratios_snapshot: dict[int, RatioRecord],
        recommended_rpm: float | None,
        recommendation_conf: float | None,
    ) -> None:
        """Evaluate a downshift event per FR-048.

        Closed-throttle downshifts have no propulsive torque model — the
        residual is computed against the rev-match target instead:

            recommended_post_rpm = recommended_rpm * ratio_to / ratio_from
            delta_rpm            = post_shift_rpm - recommended_post_rpm
            est_cost_s           = max(0, |delta_rpm| - 300) / 1000 * 0.05

        ``predicted_post_torque`` and ``measured_post_torque`` are always
        ``NULL`` for downshifts. When no predictor recommendation existed at
        shift time the row is still written with the post-shift RPM but the
        rev-match fields are ``NULL`` (FR-048 last paragraph).
        """
        # --- Step 1: Clean-downshift gate ---
        # Brake >= shift_downshift_brake_display_min OR throttle < 0.30 across
        # every frame in both windows; plus the v1 steer / slip / window-size
        # checks. The throttle-min check is replaced (closed throttle is the
        # whole point); the brake-max check is replaced (engaged brake is
        # required in many cases).
        if not self._is_clean_downshift(pre_window, post_window):
            return

        # --- Step 2: Pre-shift RPM (last frame before the shift) ---
        actual_rpm = float(
            pre_window[-1].raw.engine.get("currentRpm", pre_window[-1].raw.engine.get("rpm", 0.0))
        )

        # --- Step 3: Post-shift RPM mean ---
        post_rpms = [
            float(f.raw.engine.get("currentRpm", f.raw.engine.get("rpm", 0.0))) for f in post_window
        ]
        post_rpm_mean = sum(post_rpms) / len(post_rpms)

        # --- Step 4: Compute rev-match target if we have a recommendation ---
        recommended_post_rpm: float | None = None
        est_cost_s: float | None = None

        if (
            recommended_rpm is not None
            and gear_from in ratios_snapshot
            and gear_to in ratios_snapshot
        ):
            ratio_from = ratios_snapshot[gear_from].ratio
            ratio_to = ratios_snapshot[gear_to].ratio
            if ratio_from > 0.0:
                recommended_post_rpm = recommended_rpm * ratio_to / ratio_from
                delta_rpm = post_rpm_mean - recommended_post_rpm
                over = max(0.0, abs(delta_rpm) - _DOWNSHIFT_REV_MATCH_BAND_RPM)
                est_cost_s = over * _DOWNSHIFT_COST_PER_RPM

        # --- Step 5: Persist (always writes a row for clean downshifts) ---
        row = ShiftEventRow(
            id=None,
            session_id=session_id,
            fingerprint=fingerprint,
            shift_at=at,
            gear_from=gear_from,
            gear_to=gear_to,
            actual_rpm=actual_rpm,
            recommended_rpm=recommended_rpm,
            recommendation_conf=recommendation_conf,
            predicted_post_torque=None,
            measured_post_torque=None,
            est_cost_s=est_cost_s,
            post_shift_rpm=post_rpm_mean,
            recommended_post_rpm=recommended_post_rpm,
        )
        await self._repo.record_shift_event(row)

    def _is_clean_downshift(
        self,
        pre_window: Sequence[DecodedFrame],
        post_window: Sequence[DecodedFrame],
    ) -> bool:
        """FR-048 clean-downshift gate.

        Every frame in both windows must satisfy:
          - ``brake >= shift_downshift_brake_display_min`` OR
            ``throttle < 0.30`` (driver is in a downshift context); and
          - ``abs(steer) < shift_steer_max`` (straight-line); and
          - all four wheels' ``combinedSlip < shift_combined_slip_max``.

        The v1 throttle-min and brake-max gates are intentionally NOT applied
        — closed-throttle braking is precisely the regime this branch targets.
        """
        brake_min = self._cfg.shift_downshift_brake_display_min
        steer_max = self._cfg.shift_steer_max
        slip_max = self._cfg.shift_combined_slip_max

        for frame in list(pre_window) + list(post_window):
            inp = frame.raw.inputs
            throttle = float(inp.get("throttle", 0.0))
            brake = float(inp.get("brake", 0.0))
            # Downshift cleanliness: in the braking zone OR off-throttle.
            if brake < brake_min and throttle >= _DOWNSHIFT_CLEAN_THROTTLE_MAX:
                return False
            if abs(float(inp.get("steer", 0.0))) >= steer_max:
                return False
            wheels = frame.raw.wheels
            for corner in ("fl", "fr", "rl", "rr"):
                slip = (wheels.get(corner) or {}).get("combinedSlip", 0.0)
                if float(slip) >= slip_max:
                    return False
        return True
