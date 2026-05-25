"""T136: finish-position model. MVP: nudge by gap-to-leader heuristic."""

from __future__ import annotations

from dataclasses import dataclass

from fh6.domain.value_objects.confidence import Confidence

MODEL_VERSION = "finish-v0-gap-heuristic"
TOLERANCE_BAND = 1.0


@dataclass(slots=True)
class FinishPositionModel:
    model_version: str = MODEL_VERSION
    tolerance_band: float = TOLERANCE_BAND

    def predict(
        self,
        *,
        current_position: int,
        gap_to_leader_s: float,
        laps_remaining: int,
    ) -> tuple[int, Confidence]:
        # If far behind with few laps left, predicted finish stays put.
        # If close to leader with laps to spare, finish improves by 1.
        delta = 0
        if gap_to_leader_s < 2.0 and laps_remaining >= 2:
            delta = -1
        elif gap_to_leader_s > 8.0 and laps_remaining <= 1:
            delta = 1
        predicted = max(1, current_position + delta)
        return (
            predicted,
            Confidence(
                value=0.5, tolerance_band=self.tolerance_band, model_version=self.model_version
            ),
        )
