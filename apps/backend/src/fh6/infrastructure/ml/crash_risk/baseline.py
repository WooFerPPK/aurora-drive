"""T134: crash-risk model. Combines slip + smashable proximity heuristics."""

from __future__ import annotations

from dataclasses import dataclass

from fh6.domain.value_objects.confidence import Confidence

MODEL_VERSION = "crash-risk-v0-heuristic"
TOLERANCE_BAND = 0.1


@dataclass(slots=True)
class CrashRiskModel:
    model_version: str = MODEL_VERSION
    tolerance_band: float = TOLERANCE_BAND

    def predict(
        self,
        *,
        avg_combined_slip: float,
        smashable_velocity_diff: float,
        speed_mps: float,
    ) -> tuple[float, Confidence]:
        risk = min(
            1.0,
            max(
                0.0,
                0.3 * avg_combined_slip
                + 0.4 * min(1.0, smashable_velocity_diff / 30.0)
                + 0.3 * min(1.0, speed_mps / 90.0),
            ),
        )
        return (
            risk,
            Confidence(
                value=0.55, tolerance_band=self.tolerance_band, model_version=self.model_version
            ),
        )
