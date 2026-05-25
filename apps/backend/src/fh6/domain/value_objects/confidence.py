from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Confidence:
    value: float
    tolerance_band: float
    model_version: str

    def __post_init__(self) -> None:
        # Clarification Q4: calibrated probability that the modeled value lies
        # within `tolerance_band`. Construction refuses without all three.
        if not 0.0 <= self.value <= 1.0:
            raise ValueError(f"confidence out of [0,1]: {self.value!r}")
        if self.tolerance_band < 0:
            raise ValueError(f"tolerance_band must be >= 0: {self.tolerance_band!r}")
        if not self.model_version:
            raise ValueError("model_version must be non-empty")

    @classmethod
    def placeholder(cls) -> Confidence:
        return cls(value=0.0, tolerance_band=0.0, model_version="placeholder")
