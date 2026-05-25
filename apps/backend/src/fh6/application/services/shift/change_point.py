"""ChangePointDetector — implements the ChangePointObserver Protocol.

Watches a rolling window of recent eligible (rpm_bin, torque_nm) samples
per fingerprint. When the window's bin means diverge from the stored bin's
running mean by ≥ Z sigma over ≥ N contiguous bins, fires a callback.
After firing, training pauses for that fingerprint until reset() is called.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from fh6.domain.ports.shift_predictor_repo import BinRecord
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint
from fh6.infrastructure.config import AppConfig
from fh6.infrastructure.logging import get_logger

_log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ChangePointEvent:
    fingerprint: EngineFingerprint
    direction: str  # "positive" | "negative"
    bins_affected: int
    at: datetime


# Callback signature: invoked synchronously when a change-point fires.
ChangePointCallback = Callable[[ChangePointEvent], None]


class ChangePointDetector:
    """Detects drift in per-bin torque distributions and fires a callback.

    Maintains a rolling window (capped at WINDOW_SIZE) of (rpm_bin, torque_nm)
    samples per fingerprint. Every WINDOW_STRIDE new samples it tests whether
    the window's bin means have diverged from stored running means by ≥
    cfg.shift_change_z_threshold sigma across ≥ cfg.shift_change_bins_required
    CONTIGUOUS bins in the same direction.

    After a change-point fires, training for that fingerprint is paused
    (is_paused() returns True) until reset() is called.
    """

    WINDOW_SIZE: int = 100
    WINDOW_STRIDE: int = 25
    MIN_BIN_SAMPLES: int = 5

    def __init__(
        self,
        *,
        config: AppConfig,
        on_change_point: ChangePointCallback,
    ) -> None:
        self._cfg = config
        self._cb = on_change_point

        # Per-fingerprint rolling window: list of (rpm_bin, torque_nm).
        # Bounded to WINDOW_SIZE (oldest dropped when full).
        self._windows: dict[EngineFingerprint, list[tuple[int, float]]] = {}

        # Paused flag: once a change-point fires, training pauses until reset().
        self._paused: set[EngineFingerprint] = set()

        # Stride counter: number of new samples since last test run.
        self._since_test: dict[EngineFingerprint, int] = {}

        # Cached stored bins per fingerprint, keyed by rpm_bin.
        # Updated every time observe() is called with a non-None stored_bin.
        self._stored_by_bin: dict[EngineFingerprint, dict[int, BinRecord]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def observe(
        self,
        fp: EngineFingerprint,
        gear: int,  # accepted but not used in v1
        rpm: float,
        torque_nm: float,
        at: datetime,
        stored_bin: BinRecord | None,
    ) -> None:
        """Record one sample. May fire the callback synchronously.

        If stored_bin is None for this rpm_bin, that bin cannot be scored
        but samples still accumulate for other bins that do have stored data.
        """
        # 1. Pause guard — we skip processing entirely (but accept the call).
        if fp in self._paused:
            return

        # 2. Compute rpm_bin and cache the stored_bin if provided.
        rpm_bin = int(rpm / 100)

        if stored_bin is not None:
            fp_cache = self._stored_by_bin.setdefault(fp, {})
            fp_cache[rpm_bin] = stored_bin

        # 3. Append to rolling window (cap at WINDOW_SIZE).
        window = self._windows.setdefault(fp, [])
        window.append((rpm_bin, torque_nm))
        if len(window) > self.WINDOW_SIZE:
            window.pop(0)

        # 4. Stride gate: only run the test every WINDOW_STRIDE new samples.
        self._since_test[fp] = self._since_test.get(fp, 0) + 1
        if self._since_test[fp] < self.WINDOW_STRIDE:
            return
        self._since_test[fp] = 0

        # 5. Run the change-point test.
        self._run_test(fp, at)

    def is_paused(self, fp: EngineFingerprint) -> bool:
        """Return True if training is paused for this fingerprint."""
        return fp in self._paused

    def reset(self, fp: EngineFingerprint) -> None:
        """Clear the rolling window, paused flag, and test counter for fp.

        Called on session start (after hydrate) and on manual fingerprint reset.
        """
        self._windows.pop(fp, None)
        self._paused.discard(fp)
        self._since_test.pop(fp, None)
        # Keep _stored_by_bin — historical stored records remain valid context.

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_test(self, fp: EngineFingerprint, at: datetime) -> None:
        """Evaluate the window for drift. Fire callback if conditions met."""
        window = self._windows.get(fp, [])
        stored_cache = self._stored_by_bin.get(fp, {})

        if not window or not stored_cache:
            return

        # Group window samples by rpm_bin.
        bin_samples: dict[int, list[float]] = {}
        for rpm_bin, torque in window:
            bin_samples.setdefault(rpm_bin, []).append(torque)

        z_threshold = self._cfg.shift_change_z_threshold
        bins_required = self._cfg.shift_change_bins_required

        # Compute z-score for each bin that has enough window samples AND a stored record.
        # key = rpm_bin, value = signed z-score
        deviating: dict[int, float] = {}

        for rpm_bin, samples in bin_samples.items():
            if len(samples) < self.MIN_BIN_SAMPLES:
                continue
            stored = stored_cache.get(rpm_bin)
            if stored is None:
                continue

            # Window mean for this bin.
            window_mean = sum(samples) / len(samples)

            # Stored variance from Welford's m2: var = m2 / max(1, count-1).
            stored_variance = stored.m2_torque / max(1, stored.count - 1)
            # Guard against near-zero variance.
            denom = math.sqrt(stored_variance + 1e-9)

            z = (window_mean - stored.mean_torque_nm) / denom

            if abs(z) >= z_threshold:
                deviating[rpm_bin] = z

        if not deviating:
            return

        # Find the longest contiguous run of rpm_bins all deviating in the same direction.
        best_run: list[int] = []
        best_direction: str = "positive"

        sorted_bins = sorted(deviating.keys())

        # Try both directions.
        for direction in ("positive", "negative"):
            candidate: list[int] = []
            for rpm_bin in sorted_bins:
                z = deviating[rpm_bin]
                in_direction = (z > 0) if direction == "positive" else (z < 0)
                if not in_direction:
                    candidate = []
                    continue
                candidate.append(rpm_bin)
                # Check contiguity: all consecutive integers
                if len(candidate) >= 2 and candidate[-1] != candidate[-2] + 1:
                    # Reset — keep only the latest
                    candidate = [rpm_bin]
                if len(candidate) > len(best_run):
                    best_run = list(candidate)
                    best_direction = direction

        if len(best_run) < bins_required:
            return

        # Fire.
        self._paused.add(fp)
        event = ChangePointEvent(
            fingerprint=fp,
            direction=best_direction,
            bins_affected=len(best_run),
            at=at,
        )
        try:
            self._cb(event)
        except Exception:
            _log.exception("change_point_callback_error")
