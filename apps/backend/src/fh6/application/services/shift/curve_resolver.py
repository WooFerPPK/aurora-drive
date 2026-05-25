"""ShiftCurveResolver — fits per-gear torque curves and finds optimal upshift RPM.

Implements the CurveResolver Protocol defined in shift_predictor.py (FR-008/010).

Algorithm:
1. For each gear's BinRecords, fit a weighted cubic spline (UnivariateSpline)
   through (rpm_bin_center, q90_torque_nm) pairs, weighted by precision
   (count / (variance + 1.0)).
2. Check monotonicity via sign-changes in the derivative; retry with doubling
   smoothing factor up to 5 times before falling back to linear interpolation.
3. For each adjacent gear pair (g, g+1), find the wheel-torque crossover RPM
   via Newton's method with numerical derivative. Round to nearest 100 RPM.

This module is pure / synchronous — the ShiftPredictor caches results.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from scipy.interpolate import UnivariateSpline, interp1d

from fh6.application.services.shift.shift_predictor import ResolvedCurves
from fh6.domain.ports.shift_predictor_repo import BinRecord, RatioRecord
from fh6.infrastructure.config import AppConfig

# ---------------------------------------------------------------------------
# CurveFit value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CurveFit:
    """A fitted torque curve for a single gear."""

    spline: Any  # scipy UnivariateSpline OR a scipy interp1d fallback callable
    valid_min_rpm: float  # minimum RPM of the fitted data (clamp lower bound)
    valid_max_rpm: float  # maximum RPM of the fitted data (clamp upper bound)
    peak_torque_nm: float  # max evaluated torque across qualifying bins
    n_samples: int  # total bin samples that contributed to this fit
    # FR-011: weighted RMS of fit residuals divided by the curve's peak q90,
    # clamped to [0, 1]. Used in the recommendation confidence formula.
    normalized_residual: float = 0.0

    def evaluate(self, rpm: float) -> float:
        """Evaluate the spline at rpm; clamps to [valid_min_rpm, valid_max_rpm].

        Clamping prevents dangerous extrapolation outside the observed data range.
        """
        clamped = max(self.valid_min_rpm, min(self.valid_max_rpm, rpm))
        return float(self.spline(clamped))


# ---------------------------------------------------------------------------
# ShiftCurveResolver
# ---------------------------------------------------------------------------


class ShiftCurveResolver:
    """Fits smooth per-gear torque curves and solves for optimal upshift RPMs.

    Pure / synchronous — call from ShiftPredictor which owns the cache.
    """

    def __init__(self, *, config: AppConfig) -> None:
        self._cfg = config

    # ------------------------------------------------------------------
    # Public: fit one gear's bins into a CurveFit
    # ------------------------------------------------------------------

    def fit_curve(
        self,
        bins_for_gear: list[BinRecord],
        idle_rpm: float,
        max_rpm: float,
    ) -> CurveFit | None:
        """Fit a smooth curve for ONE gear's bin records.

        Returns None if fewer than 4 bins meet the minimum-count threshold
        (spline requires ≥ 4 knot-points to be reliable).
        """
        min_count = self._cfg.shift_bin_min_count

        # Filter to bins that have enough samples
        qualifying = [rec for rec in bins_for_gear if rec.count >= min_count]
        if len(qualifying) < 4:
            return None

        # Sort by rpm_bin so x-array is monotonically increasing
        qualifying.sort(key=lambda r: r.rpm_bin)

        # Bin center RPM: bin index i represents [i*100, (i+1)*100), center = (i+0.5)*100
        x = np.array([(rec.rpm_bin + 0.5) * 100.0 for rec in qualifying])
        y = np.array([rec.q90_torque_nm for rec in qualifying])

        # Precision weights: higher count and lower variance → higher weight.
        # variance = M2 / max(1, count - 1); +1.0 prevents div-by-zero.
        w = np.array(
            [rec.count / (rec.m2_torque / max(1.0, rec.count - 1.0) + 1.0) for rec in qualifying]
        )

        n_samples = int(sum(rec.count for rec in qualifying))
        valid_min_rpm = float(x[0])
        valid_max_rpm = float(x[-1])

        # --- Spline fitting with adaptive smoothing ---
        # Initial smoothing: mild (sum of weights * 0.5 keeps enough flexibility
        # while still suppressing noise peaks).
        s = float(np.sum(w)) * 0.5
        spline: Any = None
        used_fallback = False

        for _attempt in range(5):
            try:
                sp = UnivariateSpline(x, y, w=w, k=3, s=s)
            except Exception:
                # If scipy raises (e.g. too-constrained fit), double s and retry
                s *= 2.0
                continue

            # Check monotonicity: count sign changes in the derivative.
            # A well-behaved torque curve rises then falls (≤ 1 sign change).
            n_sign_changes = self._count_derivative_sign_changes(sp, idle_rpm, max_rpm)
            if n_sign_changes <= 1:
                spline = sp
                break
            # More than one sign change → too wiggly; double s and retry.
            s *= 2.0
        else:
            # All 5 retries exhausted — fall back to piecewise-linear interpolation.
            used_fallback = True

        if used_fallback or spline is None:
            # Piecewise-linear fallback: safe and always monotonic-ish at data points.
            lin = interp1d(x, y, kind="linear", fill_value="extrapolate", bounds_error=False)
            spline = lin

        # Peak torque: max of evaluated spline at bin centers
        peak_torque_nm = float(np.max([spline(xi) for xi in x]))

        # FR-011: normalized weighted RMS residual of the fit. Used by the
        # confidence formula. peak_q90 is the max observed (not evaluated) q90
        # across the qualifying bins; if it's non-positive the curve carries
        # no signal and we fall back to a residual of 1.0 (zero spline term).
        #
        # When we fall back to the piecewise-linear interp1d (used_fallback),
        # the fit passes through every data point so the literal residual is
        # zero — but that is misleading: the fallback was triggered precisely
        # because the data is too noisy for a smooth spline. We apply a fixed
        # 0.5 penalty in that case so the confidence reflects the degraded
        # quality of the fit.
        if used_fallback:
            normalized_residual = 0.5
        else:
            y_fit = np.array([float(spline(xi)) for xi in x])
            residuals = y - y_fit
            w_sum = float(np.sum(w))
            if w_sum > 0.0:
                weighted_rms = float(np.sqrt(np.sum(w * residuals * residuals) / w_sum))
            else:
                weighted_rms = 0.0
            peak_q90 = float(np.max(y))
            normalized_residual = weighted_rms / peak_q90 if peak_q90 > 0.0 else 1.0
            # Clamp to [0, 1] so the (1 - residual) factor stays in [0, 1].
            normalized_residual = max(0.0, min(1.0, normalized_residual))

        return CurveFit(
            spline=spline,
            valid_min_rpm=valid_min_rpm,
            valid_max_rpm=valid_max_rpm,
            peak_torque_nm=peak_torque_nm,
            n_samples=n_samples,
            normalized_residual=normalized_residual,
        )

    # ------------------------------------------------------------------
    # Public: Newton crossover
    # ------------------------------------------------------------------

    def solve_optimal(
        self,
        *,
        fit_pre: CurveFit,
        fit_post: CurveFit,
        ratio_pre: float,
        ratio_post: float,
        direction: Literal["up", "down"],
        idle_rpm: float,
        max_rpm: float,
    ) -> int | None:
        """Find the optimal shift RPM via Newton's method (FR-010, FR-045).

        `pre` is the gear you're IN; `post` is the gear you're shifting TO.
        At constant road speed, ``post_rpm = pre_rpm * ratio_post / ratio_pre``.

        - **Upshift** (``direction="up"``): ``ratio_post < ratio_pre`` so
          ``post_rpm < pre_rpm``. The pre-shift RPM is searched over
          ``[idle_rpm, max_rpm]``; seed at ``0.9 * max_rpm``. If Newton finds
          no crossover, falls back to ``max_rpm`` rounded to 100 RPM.
        - **Downshift** (``direction="down"``): ``ratio_post > ratio_pre`` so
          ``post_rpm > pre_rpm``. The pre-shift RPM is searched over
          ``[idle_rpm, max_rpm * ratio_pre / ratio_post]`` (the upper bound is
          the pre-shift RPM above which the post-shift would over-rev). Seed
          at ``0.5 * pre_rpm_max``. If ``pre_rpm_max <= idle_rpm`` the gear
          pair is unviable and ``None`` is returned. If Newton fails to
          converge but the interval is viable, falls back to
          ``0.7 * pre_rpm_max`` rounded to 100 RPM.

        Returns an int rounded to nearest 100 RPM, or ``None`` for an
        unviable downshift pair.
        """
        rpm_scale = ratio_post / ratio_pre

        # Pre-shift RPM upper bound — for downshift, capped so post-shift
        # never exceeds max_rpm (over-rev protection per FR-045).
        pre_rpm_max = max_rpm if direction == "up" else max_rpm / rpm_scale

        # Downshift viability gate: if the upper bound collapses below idle,
        # there's no valid pre-shift RPM for this gear pair.
        if direction == "down" and pre_rpm_max <= idle_rpm:
            return None

        def f(rpm: float) -> float:
            rpm_post = rpm * rpm_scale
            return fit_pre.evaluate(rpm) * ratio_pre - fit_post.evaluate(rpm_post) * ratio_post

        def _no_crossover_fallback() -> int:
            # Up: legacy behaviour — fall back to max_rpm.
            # Down: interval is viable (pre_rpm_max > idle_rpm) but Newton
            # couldn't find a root → 0.7 * pre_rpm_max rounded to 100 RPM.
            if direction == "up":
                return _fallback(max_rpm)
            return int(0.7 * pre_rpm_max // 100) * 100

        # Quick sign-change check: sample 20 points to see if a zero-crossing
        # exists in the viable pre-shift interval.
        sample_rpms = np.linspace(idle_rpm, pre_rpm_max, 20)
        f_values = np.array([f(r) for r in sample_rpms])
        signs = np.sign(f_values[f_values != 0])
        if len(signs) == 0 or np.all(signs == signs[0]):
            return _no_crossover_fallback()

        # Newton's method: 20 iterations should easily converge for smooth curves.
        # Seed depends on direction — upshifts cross over near redline, downshifts
        # nearer the middle of their (tighter) interval.
        rpm = (0.9 if direction == "up" else 0.5) * pre_rpm_max
        h = 10.0  # RPM step for numerical derivative (small relative to bin width=100)

        for _ in range(20):
            fx = f(rpm)
            if abs(fx) < 1e-3:
                return int(round(rpm / 100) * 100)

            # Numerical derivative via central difference
            fdx = (f(rpm + h) - f(rpm - h)) / (2.0 * h)
            if abs(fdx) < 1e-9:
                # Near-flat derivative — Newton cannot make progress; bail
                return _no_crossover_fallback()

            rpm_next = rpm - fx / fdx
            # Clamp to viable pre-shift interval to prevent divergence
            rpm = max(idle_rpm, min(pre_rpm_max, rpm_next))

        return _no_crossover_fallback()

    # ------------------------------------------------------------------
    # Public: orchestration
    # ------------------------------------------------------------------

    def resolve(
        self,
        bins: Mapping[tuple[int, int], BinRecord],
        ratios: Mapping[int, RatioRecord],
        idle_rpm: float,
        max_rpm: float,
    ) -> ResolvedCurves:
        """Orchestrate: fit per-gear curves, then compute crossover RPMs.

        For each adjacent gear pair (g, g+1) where BOTH fits succeed and BOTH
        ratios are present, computes the optimal upshift RPM and a confidence.
        Returns ResolvedCurves suitable for caching in ShiftPredictor.
        """
        # Group bin records by gear
        by_gear: dict[int, list[BinRecord]] = {}
        for (g, _rpm_bin), rec in bins.items():
            by_gear.setdefault(g, []).append(rec)

        # Fit per-gear splines
        fits: dict[int, CurveFit] = {}
        for g, recs in by_gear.items():
            fit = self.fit_curve(recs, idle_rpm, max_rpm)
            if fit is not None:
                fits[g] = fit

        optimal_rpm_by_gear: dict[int, int] = {}
        confidence_by_gear: dict[int, float] = {}
        samples_by_gear_pair: dict[tuple[int, int], int] = {}

        # Compute crossover for each adjacent gear pair where both fits + ratios exist
        for g in sorted(fits.keys()):
            gp1 = g + 1
            if gp1 not in fits:
                continue
            if g not in ratios or gp1 not in ratios:
                continue

            rpm = self.solve_optimal(
                fit_pre=fits[g],
                fit_post=fits[gp1],
                ratio_pre=ratios[g].ratio,
                ratio_post=ratios[gp1].ratio,
                direction="up",
                idle_rpm=idle_rpm,
                max_rpm=max_rpm,
            )
            # Upshift never returns None (no viability gate), but guard for safety.
            if rpm is None:
                continue
            optimal_rpm_by_gear[g] = rpm

            # FR-011 confidence: min(1, samples_pair / 400)
            #                  * (1 - normalized_spline_residual)
            #                  * (1 - drift_penalty)
            # samples_pair = top-third(g) + bottom-third(g+1) (partition by RPM thirds).
            # Spline residual is the larger of the two gears' normalized residuals
            # (the bottleneck for the pair). Drift penalty is applied post-hoc by
            # the predictor at decoration time so the cache stays drift-agnostic.
            samples_pair = _samples_partition(
                by_gear.get(g, []), "top", idle_rpm, max_rpm
            ) + _samples_partition(by_gear.get(gp1, []), "bottom", idle_rpm, max_rpm)
            sample_term = min(1.0, samples_pair / 400.0)
            residual_pair = max(fits[g].normalized_residual, fits[gp1].normalized_residual)
            spline_term = max(0.0, 1.0 - residual_pair)
            confidence_by_gear[g] = max(0.0, min(1.0, sample_term * spline_term))
            # samples_by_gear_pair retains the total-bin sum used for stage
            # calculation and the training meter — that's a UI-facing number,
            # not the FR-011 partition.
            samples_by_gear_pair[(g, gp1)] = fits[g].n_samples + fits[gp1].n_samples

        # FR-046: parallel downshift loop. For each fitted gear g where gear
        # g-1 is also fitted (and g >= 2), solve the downshift crossover.
        # Unviable pairs (post_rpm_max < idle_rpm per FR-045) return None
        # and are silently skipped — the key is omitted from the wire (FR-047).
        # Confidence uses the same FR-011 formula as upshift with the partition
        # mirrored: samples_pair = bottom-third(g) + top-third(g-1).
        by_gear_downshift: dict[int, int] = {}
        confidence_by_gear_downshift: dict[int, float] = {}
        for g in sorted(fits.keys()):
            gm1 = g - 1
            if gm1 < 1 or gm1 not in fits:
                continue
            if g not in ratios or gm1 not in ratios:
                continue

            rpm_down = self.solve_optimal(
                fit_pre=fits[g],
                fit_post=fits[gm1],
                ratio_pre=ratios[g].ratio,
                ratio_post=ratios[gm1].ratio,
                direction="down",
                idle_rpm=idle_rpm,
                max_rpm=max_rpm,
            )
            if rpm_down is None:
                # Unviable pair — FR-045 viability gate triggered. Omit the key.
                continue
            by_gear_downshift[g] = rpm_down

            samples_pair_down = _samples_partition(
                by_gear.get(g, []), "bottom", idle_rpm, max_rpm
            ) + _samples_partition(by_gear.get(gm1, []), "top", idle_rpm, max_rpm)
            sample_term_down = min(1.0, samples_pair_down / 400.0)
            residual_pair_down = max(fits[g].normalized_residual, fits[gm1].normalized_residual)
            spline_term_down = max(0.0, 1.0 - residual_pair_down)
            confidence_by_gear_downshift[g] = max(
                0.0, min(1.0, sample_term_down * spline_term_down)
            )

        # Determine learning stage
        if not fits:
            stage = "fallback"
        elif any(n >= self._cfg.shift_pair_learned_samples for n in samples_by_gear_pair.values()):
            stage = "learned"
        else:
            stage = "prior"

        return ResolvedCurves(
            optimal_rpm_by_gear=optimal_rpm_by_gear,
            confidence_by_gear=confidence_by_gear,
            stage=stage,
            samples_by_gear_pair=samples_by_gear_pair,
            by_gear_downshift=by_gear_downshift,
            confidence_by_gear_downshift=confidence_by_gear_downshift,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _count_derivative_sign_changes(
        spline: Any,
        idle_rpm: float,
        max_rpm: float,
    ) -> int:
        """Count sign changes in spline's first derivative over [idle_rpm, max_rpm].

        Uses 50 evenly-spaced sample points. ≤ 1 sign change = acceptable shape
        (monotone, or rises-then-falls). > 1 = too wiggly, triggers retry.
        """
        rpms = np.linspace(idle_rpm, max_rpm, 50)
        try:
            derivs = spline.derivative()(rpms)
        except AttributeError:
            # interp1d does not have .derivative(); treat as acceptable (already a fallback)
            return 0

        signs = np.sign(derivs)
        non_zero = signs[signs != 0]
        if len(non_zero) < 2:
            return 0
        sign_changes = int(np.sum(non_zero[1:] != non_zero[:-1]))
        return sign_changes


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------


def _fallback(max_rpm: float) -> int:
    """Round max_rpm to the nearest 100 RPM and return as int."""
    return int(round(max_rpm / 100) * 100)


def _samples_partition(
    bins_for_gear: list[BinRecord],
    position: Literal["top", "bottom"],
    idle_rpm: float,
    max_rpm: float,
) -> int:
    """FR-011 samples partition: count bins in the top/bottom third of a gear's RPM range.

    Thirds are defined relative to [idle_rpm, max_rpm]:
      - "bottom" = bins where ``rpm_bin * 100 < idle_rpm + (max-idle)/3``
      - "top"    = bins where ``rpm_bin * 100 >= idle_rpm + 2*(max-idle)/3``

    Returns the sum of ``count`` across qualifying bins (cast to ``int``).
    """
    third = (max_rpm - idle_rpm) / 3.0
    if position == "top":
        threshold = idle_rpm + 2.0 * third
        return int(sum(b.count for b in bins_for_gear if b.rpm_bin * 100.0 >= threshold))
    # "bottom"
    threshold = idle_rpm + third
    return int(sum(b.count for b in bins_for_gear if b.rpm_bin * 100.0 < threshold))
