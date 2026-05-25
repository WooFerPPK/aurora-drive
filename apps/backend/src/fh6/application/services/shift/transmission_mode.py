"""TransmissionModeInferer — classifies a fingerprint's transmission mode from
the dispersion of clean-upshift pre-shift RPMs (FR-041).

A low stdev in pre-shift RPM across multiple gear pairs implies consistent
shift points characteristic of automatic or paddle-shift transmission.
High stdev implies human-variable shift points characteristic of a manual.

The inferer is in-memory only.  The predictor reads any *persisted* result
from the DB for the wire decoration, falling back to the in-memory result
when persisted data is absent or stale (Task 10 wiring).
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from statistics import median, stdev

from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint
from fh6.infrastructure.config import AppConfig

# ---------------------------------------------------------------------------
# Public value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TransmissionModeResult:
    """Snapshot of the transmission mode inference for one fingerprint."""

    mode: str  # "auto" | "manual" | "unknown"
    confidence: float  # 0.0 – 1.0
    sample_count: int  # total non-1→2 samples stored for this fingerprint


# ---------------------------------------------------------------------------
# TransmissionModeInferer
# ---------------------------------------------------------------------------


class TransmissionModeInferer:
    """Classifies a fingerprint's transmission mode from upshift RPM dispersion.

    Maintains a per-(fingerprint, gear_pair) ring buffer of pre-shift RPMs.
    1→2 upshifts are excluded (launch-noise, per FR-041 implementation note).
    Classification requires at least ``config.shift_trans_mode_min_samples``
    samples in at least one gear pair ring.

    Typical lifecycle
    -----------------
    1. ``observe_clean_upshift(...)`` for each qualified upshift event.
    2. ``infer(fp)`` to query the current classification.
    3. ``drop_fingerprint(fp)`` when the fingerprint is evicted from memory.
    4. ``hydrate(fp, result)`` is a no-op; the inferer accumulates fresh data.
    """

    def __init__(self, *, config: AppConfig) -> None:
        self._cfg = config
        # fingerprint -> gear_pair (tuple[int,int]) -> deque[float]
        self._rings: dict[EngineFingerprint, dict[tuple[int, int], deque[float]]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=config.shift_trans_mode_ring_cap))
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def observe_clean_upshift(
        self,
        fp: EngineFingerprint,
        gear_from: int,
        gear_to: int,
        pre_shift_rpm: float,
    ) -> None:
        """Record one clean upshift pre-shift RPM for the given fingerprint.

        Silently ignores:
        - Malformed gear transitions (gear_to != gear_from + 1, or gear_from ≤ 0).
        - 1→2 transitions (launch noise, per FR-041 implementation note).
        """
        if gear_from <= 0 or gear_to != gear_from + 1:
            return
        if gear_from == 1:  # exclude 1→2 (launch noise — FR-041 implementation note)
            return
        self._rings[fp][(gear_from, gear_to)].append(pre_shift_rpm)

    def infer(self, fp: EngineFingerprint) -> TransmissionModeResult:
        """Return the current transmission mode classification for *fp*.

        Returns ``("unknown", 0.0, n)`` if no gear pair has accumulated
        ``shift_trans_mode_min_samples`` samples yet.

        Classification logic:
        - Compute per-pair stdev for each pair with enough samples.
        - Take the median of those stdevs (robust against one outlier pair).
        - Compare against ``shift_trans_mode_auto_stdev_rpm``.
        - Confidence scales linearly with total sample count, capped at 1.0
          at 30 samples.
        """
        pair_rings = self._rings.get(fp, {})
        total_samples = sum(len(r) for r in pair_rings.values())

        usable_pairs = [
            r for r in pair_rings.values() if len(r) >= self._cfg.shift_trans_mode_min_samples
        ]
        if not usable_pairs:
            return TransmissionModeResult("unknown", 0.0, total_samples)

        per_pair_stdev = [stdev(r) for r in usable_pairs]
        mode_score = median(per_pair_stdev)
        mode = "auto" if mode_score < self._cfg.shift_trans_mode_auto_stdev_rpm else "manual"
        confidence = min(1.0, total_samples / 30.0)
        return TransmissionModeResult(mode, confidence, total_samples)

    def drop_fingerprint(self, fp: EngineFingerprint) -> None:
        """Drop in-memory state for one fingerprint (called from ShiftPredictor.reset)."""
        self._rings.pop(fp, None)

    def hydrate(self, fp: EngineFingerprint, persisted: TransmissionModeResult) -> None:
        """No-op: the inferer is purely empirical.

        The persisted result is read by the predictor directly when constructing
        the wire decoration; the inferer accumulates fresh data in the new session.
        """
        return None
