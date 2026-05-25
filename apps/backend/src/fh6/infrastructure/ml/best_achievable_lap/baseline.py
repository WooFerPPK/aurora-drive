"""T135: best-achievable-lap baseline. Sum-of-sector-bests model."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from fh6.domain.value_objects.confidence import Confidence

MODEL_VERSION = "best-achievable-lap-v0-sector-mins"
TOLERANCE_BAND = 0.4


@dataclass(slots=True)
class BestAchievableLapModel:
    model_version: str = MODEL_VERSION
    tolerance_band: float = TOLERANCE_BAND

    def predict(self, sector_best_times: Sequence[float]) -> tuple[float, Confidence]:
        if not sector_best_times:
            return (
                0.0,
                Confidence(
                    value=0.0, tolerance_band=self.tolerance_band, model_version=self.model_version
                ),
            )
        return (
            sum(sector_best_times),
            Confidence(
                value=0.7, tolerance_band=self.tolerance_band, model_version=self.model_version
            ),
        )
