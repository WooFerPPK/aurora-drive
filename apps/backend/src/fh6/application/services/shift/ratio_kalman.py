"""RatioKalman — per-gear scalar Kalman filter for gear ratio estimation (FR-006, FR-007).

Estimates r = rpm / speed_mps for each (EngineFingerprint, gear) pair.
Gear ratios are physically constant within a fingerprint, so process noise
is tiny. After a re-gear (tune change), the filter re-locks within ~30
updates by temporarily inflating process noise when residuals stay large.

Typical lifecycle
-----------------
1. ``hydrate(fp, records)`` to restore state from the repo at startup.
2. ``update(fp, gear, ratio_measurement)`` for each eligible frame.
3. ``read(fp, gear)`` to query the current estimate.
4. ``await flush(repo)`` periodically to persist.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from fh6.domain.ports.shift_predictor_repo import RatioRecord, ShiftPredictorRepository
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint

# ---------------------------------------------------------------------------
# Public value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RatioReading:
    """Snapshot of the filter state for one (fp, gear)."""

    ratio: float
    variance: float
    locked: bool  # True iff variance < lock_var_threshold AND mean stable


# ---------------------------------------------------------------------------
# Internal mutable state per (EngineFingerprint, gear)
# ---------------------------------------------------------------------------


class _GearState:
    """All mutable Kalman state for a single (fingerprint, gear) pair.

    Not exported. Consumed only by RatioKalman.
    """

    __slots__ = (
        "P",  # current variance
        # Re-lock fields
        "_relock_consecutive",  # count of consecutive large-residual updates
        "_relock_inflate_remaining",  # how many inflated-Q updates remain
        "_ring",  # deque of recent x estimates (stability window)
        "_ring_cap",  # max capacity of ring
        "x",  # current ratio estimate
    )

    def __init__(self, x: float, P: float, ring_cap: int) -> None:
        self.x: float = x
        self.P: float = P
        self._ring: deque[float] = deque(maxlen=ring_cap)
        self._ring_cap: int = ring_cap
        self._relock_consecutive: int = 0
        self._relock_inflate_remaining: int = 0


# ---------------------------------------------------------------------------
# RatioKalman
# ---------------------------------------------------------------------------


class RatioKalman:
    """Per-gear scalar Kalman filter for gear ratio estimation.

    All constructor parameters are keyword-only and have physics-motivated
    defaults. See module docstring for lifecycle.

    Parameters
    ----------
    process_noise:
        Q — tiny because ratios are physically constant within a tune.
    measurement_noise:
        R — reflects frame-to-frame ratio jitter (rpm / speed). Default
        8.0 allows locking within ~80 noiseless updates (P_ss ≈ 0.003).
    lock_var_threshold:
        Variance must be below this value to be considered locked.
    stability_window:
        Number of recent estimates to examine for stability.
    stability_band_pct:
        All estimates in window must be within ±(band_pct * x) of current x.
    relock_residual_sigma:
        Standardised residual threshold to trigger re-lock inflation.
    relock_consecutive_n:
        How many consecutive large-residual frames before inflating Q.
    relock_inflate_factor:
        Q multiplier when re-locking (makes K → 1, trusts measurement).
    relock_inflate_steps:
        How many updates to keep the inflated Q.
    """

    def __init__(
        self,
        *,
        process_noise: float = 1e-6,
        measurement_noise: float = 8.0,
        lock_var_threshold: float = 0.1,
        stability_window: int = 50,
        stability_band_pct: float = 0.005,
        relock_residual_sigma: float = 3.0,
        relock_consecutive_n: int = 10,
        relock_inflate_factor: float = 1e6,
        relock_inflate_steps: int = 5,
    ) -> None:
        self._Q_base: float = process_noise
        self._R: float = measurement_noise
        self._lock_var: float = lock_var_threshold
        self._stability_window: int = stability_window
        self._stability_band_pct: float = stability_band_pct
        self._relock_sigma: float = relock_residual_sigma
        self._relock_n: int = relock_consecutive_n
        self._relock_factor: float = relock_inflate_factor
        self._relock_steps: int = relock_inflate_steps

        # State keyed by (EngineFingerprint, gear).
        self._states: dict[tuple[EngineFingerprint, int], _GearState] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, fp: EngineFingerprint, gear: int, ratio_measurement: float) -> None:
        """Feed one ratio measurement into the filter for (fp, gear).

        On first call for a (fp, gear) pair, initialises the filter with
        x = measurement and P = R (no prior information).
        """
        key = (fp, gear)
        state = self._states.get(key)
        if state is None:
            state = _GearState(
                x=ratio_measurement,
                P=self._R,
                ring_cap=self._stability_window,
            )
            self._states[key] = state
            # Record initial estimate in ring.
            state._ring.append(ratio_measurement)
            return

        # Select process noise (inflated during re-lock)
        Q = (
            self._Q_base * self._relock_factor
            if state._relock_inflate_remaining > 0
            else self._Q_base
        )

        # ------------------------------------------------------------------
        # Kalman predict step
        # ------------------------------------------------------------------
        P_pred = state.P + Q

        # ------------------------------------------------------------------
        # Kalman update step
        # ------------------------------------------------------------------
        innovation = ratio_measurement - state.x
        K = P_pred / (P_pred + self._R)
        x_new = state.x + K * innovation
        P_new = (1.0 - K) * P_pred

        # ------------------------------------------------------------------
        # Re-lock heuristic — check BEFORE we commit the new state
        # ------------------------------------------------------------------
        innov_variance = P_pred + self._R
        standardised = abs(innovation) / math.sqrt(innov_variance)

        if standardised > self._relock_sigma:
            state._relock_consecutive += 1
            if state._relock_consecutive >= self._relock_n:
                # Trigger re-lock: inflate Q for the next N steps
                state._relock_inflate_remaining = self._relock_steps
                state._relock_consecutive = 0
                state._ring.clear()  # reset stability ring
        else:
            state._relock_consecutive = 0

        # Decrement inflation counter if active (counts down each update)
        if state._relock_inflate_remaining > 0:
            state._relock_inflate_remaining -= 1

        # Commit updated state
        state.x = x_new
        state.P = P_new
        state._ring.append(x_new)

    def read(self, fp: EngineFingerprint, gear: int) -> RatioReading | None:
        """Return the current estimate for (fp, gear), or None if unobserved."""
        state = self._states.get((fp, gear))
        if state is None:
            return None
        return RatioReading(
            ratio=state.x,
            variance=state.P,
            locked=self._is_locked(state),
        )

    def snapshot(self, fp: EngineFingerprint) -> dict[int, RatioRecord]:
        """Per-gear current estimate for fp, ready to persist.

        Returns a dict keyed by gear with one RatioRecord each.
        """
        now = datetime.now(tz=UTC)
        result: dict[int, RatioRecord] = {}
        for (f, gear), state in self._states.items():
            if f != fp:
                continue
            result[gear] = RatioRecord(
                fingerprint=fp,
                gear=gear,
                ratio=state.x,
                variance=state.P,
                last_updated=now,
            )
        return result

    def hydrate(self, fp: EngineFingerprint, records: Sequence[RatioRecord]) -> None:
        """Restore filter state from persisted records.

        Replaces any existing in-memory state for this fingerprint. The
        stability ring buffer is left empty after hydration; it re-fills as
        new updates arrive.
        """
        # Drop existing state for this fingerprint
        keys_to_remove = [k for k in self._states if k[0] == fp]
        for k in keys_to_remove:
            del self._states[k]

        for rec in records:
            state = _GearState(
                x=rec.ratio,
                P=rec.variance,
                ring_cap=self._stability_window,
            )
            self._states[(fp, rec.gear)] = state

    async def flush(self, repo: ShiftPredictorRepository) -> None:
        """Persist all in-memory estimates via repo.upsert_ratio.

        One call per observed (fp, gear). The in-memory state is retained
        after flushing.
        """
        now = datetime.now(tz=UTC)
        for (fp, gear), state in self._states.items():
            rec = RatioRecord(
                fingerprint=fp,
                gear=gear,
                ratio=state.x,
                variance=state.P,
                last_updated=now,
            )
            await repo.upsert_ratio(rec)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _is_locked(self, state: _GearState) -> bool:
        """True iff variance is below threshold AND the ring is full and stable."""
        if self._lock_var <= state.P:
            return False

        ring = state._ring
        # Must have filled the entire stability window
        if len(ring) < self._stability_window:
            return False

        # All estimates in ring must be within ±band_pct * x of the current x
        band = self._stability_band_pct * abs(state.x)
        x = state.x
        return all(abs(v - x) <= band for v in ring)
