"""T137: CalibrationJob (research R-9, Clarification Q4).

Builds a 10-bin reliability diagram per model against a held-out
replay corpus. Models whose bins drift > ±10 percentage points are
gated to `model_version="uncalibrated-{name}-{rev}"`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(slots=True)
class ReliabilityPoint:
    bin_low: float
    bin_high: float
    predicted_mean: float
    observed_rate: float
    n: int


@dataclass(slots=True)
class CalibrationReport:
    model_version: str
    bins: list[ReliabilityPoint]
    max_abs_drift: float
    is_calibrated: bool


SLACK_PP = 0.10  # ±10 percentage points (Q4)


def reliability_diagram(
    *,
    predictions: Sequence[float],
    outcomes: Sequence[int],
    n_bins: int = 10,
) -> list[ReliabilityPoint]:
    if len(predictions) != len(outcomes):
        raise ValueError("predictions and outcomes must align")
    if not predictions:
        return []
    bins: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for p, o in zip(predictions, outcomes, strict=True):
        idx = min(n_bins - 1, max(0, int(p * n_bins)))
        bins[idx].append((p, o))
    out: list[ReliabilityPoint] = []
    for i, samples in enumerate(bins):
        lo = i / n_bins
        hi = (i + 1) / n_bins
        if not samples:
            continue
        pmean = sum(p for p, _ in samples) / len(samples)
        orate = sum(o for _, o in samples) / len(samples)
        out.append(
            ReliabilityPoint(
                bin_low=lo,
                bin_high=hi,
                predicted_mean=pmean,
                observed_rate=orate,
                n=len(samples),
            )
        )
    return out


def evaluate_calibration(
    *,
    model_name: str,
    revision: str,
    predictions: Sequence[float],
    outcomes: Sequence[int],
) -> CalibrationReport:
    bins = reliability_diagram(predictions=predictions, outcomes=outcomes)
    max_drift = max((abs(b.predicted_mean - b.observed_rate) for b in bins), default=0.0)
    calibrated = max_drift <= SLACK_PP
    version = f"{model_name}-{revision}" if calibrated else f"uncalibrated-{model_name}-{revision}"
    return CalibrationReport(
        model_version=version,
        bins=bins,
        max_abs_drift=max_drift,
        is_calibrated=calibrated,
    )


__all__ = ["CalibrationReport", "ReliabilityPoint", "evaluate_calibration", "reliability_diagram"]
