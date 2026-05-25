"""T132: lap-residual model. MVP returns the rolling-mean of recent
lap times as the prediction, with a fixed 0.3 s tolerance band."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from fh6.domain.value_objects.confidence import Confidence

MODEL_VERSION = "lap-residual-v0-mean"
TOLERANCE_BAND = 0.3


@dataclass(slots=True)
class LapResidualModel:
    model_version: str = MODEL_VERSION
    tolerance_band: float = TOLERANCE_BAND

    def predict(self, recent_lap_times: Sequence[float]) -> tuple[float, Confidence]:
        if not recent_lap_times:
            return (
                0.0,
                Confidence(
                    value=0.0, tolerance_band=self.tolerance_band, model_version=self.model_version
                ),
            )
        n = len(recent_lap_times)
        mean = sum(recent_lap_times) / n
        # Confidence rises with sample count up to 0.8.
        conf = min(0.8, 0.2 + 0.05 * n)
        return (
            mean,
            Confidence(
                value=conf, tolerance_band=self.tolerance_band, model_version=self.model_version
            ),
        )
