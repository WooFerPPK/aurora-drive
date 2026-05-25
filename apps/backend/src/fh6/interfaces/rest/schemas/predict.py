"""Pydantic wire models for `/api/predict` (API spec §6)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from fh6.interfaces.rest.schemas import WireModel


class PredictionEnvelope(WireModel):
    kind: str
    value: float
    confidence: float
    toleranceBand: float
    modelVersion: str
    inputs: list[str]


class LapPrediction(WireModel):
    """One projected lap with its own confidence band (api-contract §6)."""

    lap: int = Field(ge=0)
    time_s: float = Field(ge=0.0)
    lower_s: float = Field(ge=0.0)
    upper_s: float = Field(ge=0.0)
    confidence: float = Field(ge=0.0, le=1.0)


class LapPredictionResponse(WireModel):
    """Multi-lap projection response (api-contract §6).

    Replaces the legacy `PredictionEnvelope`-based single-value shape; the
    handler still emits the old shape until Task 1C.2 rewires it.
    """

    predictions: list[LapPrediction]
    predictedAt: float
    limiter: str | None = None
    modelVersion: str
    inputs: list[str]


class TireFailurePerCorner(WireModel):
    wear: float = Field(ge=0.0, le=1.0)
    failureAtLap: int | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class TireFailurePredictionResponse(WireModel):
    """Per-corner tire-failure projection.

    `perCorner` maps each wheel (fl, fr, rl, rr) to its current wear,
    a projected lap when wear hits 1.0 (None for free-roam / cold
    session), and the model's confidence. `limitingCorner` is the
    wheel with the earliest projected failure (or the highest wear if
    no laps yet).
    """

    perCorner: dict[str, TireFailurePerCorner]
    limitingCorner: str | None = None
    modelVersion: str
    inputs: list[str]


class FinishPredictionResponse(PredictionEnvelope):
    kind: Literal["finish"] = "finish"


class CrashRiskPredictionResponse(PredictionEnvelope):
    kind: Literal["crashRisk"] = "crashRisk"


class BestAchievableLapResponse(PredictionEnvelope):
    kind: Literal["bestAchievableLap"] = "bestAchievableLap"


class WhatIfTweak(WireModel):
    kind: str
    delta: float


class WhatIfRequest(WireModel):
    sessionId: str
    fromS: float = Field(alias="from", default=0.0)
    toS: float = Field(alias="to", default=60.0)
    tweaks: list[WhatIfTweak]


class WhatIfPerTweak(WireModel):
    kind: str
    deltaS: float


class WhatIfResponse(WireModel):
    sessionId: str
    lapDeltaS: float
    confidence: float
    toleranceBand: float
    modelVersion: str
    perTweak: list[WhatIfPerTweak]
    replayId: str


__all__ = [
    "BestAchievableLapResponse",
    "CrashRiskPredictionResponse",
    "FinishPredictionResponse",
    "LapPrediction",
    "LapPredictionResponse",
    "PredictionEnvelope",
    "TireFailurePerCorner",
    "TireFailurePredictionResponse",
    "WhatIfPerTweak",
    "WhatIfRequest",
    "WhatIfResponse",
    "WhatIfTweak",
]
