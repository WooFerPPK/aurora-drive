"""T130: re-export of the domain `Model` Protocol with concrete helpers
for baselines used by US5.

A baseline does not require a trained scikit-learn model — many simply
integrate raw signals into per-frame features with a declared tolerance
band and model version. This module pins the metadata contract."""

from __future__ import annotations

from dataclasses import dataclass

from fh6.domain.value_objects.confidence import Confidence


@dataclass(slots=True)
class PredictionResult:
    value: float
    confidence: Confidence
    inputs: list[str]


__all__ = ["Confidence", "PredictionResult"]
