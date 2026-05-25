"""T138: unit test for calibration reliability (Clarification Q4 / SC-005a)."""

from __future__ import annotations

from fh6.infrastructure.ml.calibration import evaluate_calibration, reliability_diagram


def test_perfectly_calibrated_passes_slack() -> None:
    # 10 bins, each populated by 100 samples whose observed rate equals
    # the bin's predicted mean (to within numerical precision).
    preds: list[float] = []
    outs: list[int] = []
    for i in range(10):
        center = i / 10 + 0.05
        positives = int(round(center * 100))
        preds.extend([center] * 100)
        outs.extend([1] * positives + [0] * (100 - positives))
    bins = reliability_diagram(predictions=preds, outcomes=outs)
    assert len(bins) == 10
    report = evaluate_calibration(
        model_name="tire-wear",
        revision="v0-slip-energy",
        predictions=preds,
        outcomes=outs,
    )
    assert report.is_calibrated
    assert "uncalibrated" not in report.model_version


def test_drift_above_10pp_gates_to_uncalibrated_version() -> None:
    # Predict everything 0.5; observe 1.0 → 50pp drift.
    preds = [0.5] * 100
    outs = [1] * 100
    report = evaluate_calibration(
        model_name="tire-wear",
        revision="v0-slip-energy",
        predictions=preds,
        outcomes=outs,
    )
    assert not report.is_calibrated
    assert report.model_version.startswith("uncalibrated-")
    assert report.max_abs_drift >= 0.10
