"""T150: DriverFingerprintModel.

Aggregates driver style from session-level metrics that exist in
free-roam as well as racing (distance, duration, top speed). Lap
counts are used only as a tiebreaker when they exist; they never
gate whether the model produces a fingerprint.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from fh6.domain.entities.session import Session
from fh6.domain.value_objects.confidence import Confidence

MODEL_VERSION = "driver-fingerprint-v1"
TOLERANCE_BAND = 0.1
TRAITS: tuple[str, ...] = ("smooth", "brave", "early", "patient", "precise", "consist")

# Minimum data to emit a non-empty fingerprint. Below this we still
# return zeros + zero confidence so the API stays well-shaped, but
# callers can decide to suppress cosmetic fields.
MIN_DISTANCE_M = 1_000.0
MIN_SECONDS = 60.0


@dataclass(slots=True)
class FingerprintResult:
    fingerprint: dict[str, float]
    confidence: Confidence
    laps_analyzed: int
    distance_analyzed_m: float
    seconds_analyzed: float

    @property
    def has_data(self) -> bool:
        return self.distance_analyzed_m >= MIN_DISTANCE_M or self.seconds_analyzed >= MIN_SECONDS


class DriverFingerprintModel:
    model_version: str = MODEL_VERSION
    tolerance_band: float = TOLERANCE_BAND

    def fit(self, sessions: Sequence[Session]) -> FingerprintResult:
        total_distance = sum(s.distance_m for s in sessions)
        total_seconds = sum((s.duration_s or 0.0) for s in sessions)
        laps = sum(s.lap_count for s in sessions)

        if total_distance <= 0.0 and total_seconds <= 0.0:
            return FingerprintResult(
                fingerprint={t: 0.0 for t in TRAITS},
                confidence=Confidence(
                    value=0.0,
                    tolerance_band=self.tolerance_band,
                    model_version=self.model_version,
                ),
                laps_analyzed=0,
                distance_analyzed_m=0.0,
                seconds_analyzed=0.0,
            )

        # MVP heuristic: session-aggregate-driven. The real feature
        # pipeline (per-frame inputs/g-loads) replaces this later; the
        # contract is the trait dict shape, not the formula.
        top_speed = max((s.top_speed_mps for s in sessions), default=0.0)
        # Avg cruising speed (m/s) — distance / time. Cheap proxy for
        # "comfort at speed" which feeds brave + precise.
        avg_speed = total_distance / total_seconds if total_seconds > 0 else 0.0
        # Variability proxy: stdev of per-session top speeds. Used as
        # an inverse proxy for consistency (less variation = more
        # consistent). Falls back to 0 when only one session.
        speeds = [s.top_speed_mps for s in sessions]
        if len(speeds) > 1:
            mean = sum(speeds) / len(speeds)
            var = sum((x - mean) ** 2 for x in speeds) / len(speeds)
            speed_variation = var**0.5
        else:
            speed_variation = 0.0

        # Best-lap signal — only meaningful when laps were recorded.
        best_lap = min(
            (s.best_lap_s for s in sessions if s.best_lap_s is not None),
            default=None,
        )

        # Trait scoring. Each value is squashed to [0, 1].
        trait_scores: dict[str, float] = {
            # Smooth: rewards steady cruising speed (high avg, low variation).
            "smooth": _clamp01(
                0.35 + min(0.45, avg_speed / 40.0) - min(0.2, speed_variation / 30.0)
            ),
            # Brave: top speed + distance covered.
            "brave": _clamp01(
                0.30 + min(0.45, top_speed / 90.0) + min(0.25, total_distance / 50_000.0)
            ),
            # Early: rewards laps when they exist (early apex / fast lap
            # times), otherwise sits near neutral.
            "early": _clamp01(
                0.45
                + (0.25 if best_lap is not None and best_lap < 80.0 else 0.0)
                + min(0.15, total_seconds / 3_600.0)
            ),
            # Patient: rewards long sessions (willingness to stay out).
            "patient": _clamp01(0.40 + min(0.45, total_seconds / 1_800.0)),
            # Precise: rewards distance per session (long uninterrupted
            # drives) and lap completions.
            "precise": _clamp01(
                0.35 + min(0.35, total_distance / 20_000.0) + min(0.20, laps / 25.0)
            ),
            # Consist: inverse of speed_variation, scaled by data volume.
            "consist": _clamp01(
                0.30 + min(0.45, total_seconds / 3_600.0) - min(0.20, speed_variation / 25.0)
            ),
        }

        # Confidence ramps with distance OR duration, whichever is larger.
        data_volume = max(total_distance / 50_000.0, total_seconds / 3_600.0)
        conf = min(0.85, 0.30 + min(0.55, data_volume))

        return FingerprintResult(
            fingerprint=trait_scores,
            confidence=Confidence(
                value=conf,
                tolerance_band=self.tolerance_band,
                model_version=self.model_version,
            ),
            laps_analyzed=laps,
            distance_analyzed_m=total_distance,
            seconds_analyzed=total_seconds,
        )


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


__all__ = [
    "MIN_DISTANCE_M",
    "MIN_SECONDS",
    "MODEL_VERSION",
    "TRAITS",
    "DriverFingerprintModel",
    "FingerprintResult",
]
