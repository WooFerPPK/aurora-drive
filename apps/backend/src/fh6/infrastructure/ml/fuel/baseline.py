"""T133: fuel consumption baseline. Linear extrapolation from the
already-burned fraction over the elapsed race time."""

from __future__ import annotations

from dataclasses import dataclass

from fh6.domain.value_objects.confidence import Confidence

MODEL_VERSION = "fuel-v0-linear"
TOLERANCE_BAND = 0.05


@dataclass(slots=True)
class FuelConsumptionModel:
    model_version: str = MODEL_VERSION
    tolerance_band: float = TOLERANCE_BAND

    def predict(
        self,
        *,
        fuel_now: float,
        fuel_start: float,
        elapsed_s: float,
        race_remaining_s: float,
    ) -> tuple[float, Confidence]:
        if elapsed_s <= 0 or fuel_now <= 0:
            return (
                fuel_now,
                Confidence(
                    value=0.0, tolerance_band=self.tolerance_band, model_version=self.model_version
                ),
            )
        burn_rate = max(0.0, (fuel_start - fuel_now) / elapsed_s)
        projected = max(0.0, fuel_now - burn_rate * race_remaining_s)
        conf = min(0.85, 0.3 + min(1.0, elapsed_s / 600.0) * 0.55)
        return (
            projected,
            Confidence(
                value=conf, tolerance_band=self.tolerance_band, model_version=self.model_version
            ),
        )
