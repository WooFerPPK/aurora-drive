from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from fh6.domain.value_objects.confidence import Confidence
from fh6.domain.value_objects.ids import SessionId


class PredictionKind(StrEnum):
    LAP = "lap"
    FUEL = "fuel"
    TIRE_FAILURE = "tireFailure"
    FINISH = "finish"
    CRASH_RISK = "crashRisk"
    BEST_ACHIEVABLE_LAP = "bestAchievableLap"


@dataclass(slots=True)
class Prediction:
    id: str
    kind: PredictionKind
    session_id: SessionId
    predicted_at_session_seconds: float
    payload: dict[str, object]
    confidence: Confidence
    inputs: list[str] = field(default_factory=list)
