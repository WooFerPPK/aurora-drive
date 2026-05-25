"""Pydantic wire models for `/api/predict/shift*` (FR-021, FR-022, FR-023, FR-051)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from fh6.interfaces.rest.schemas import WireModel


class Fingerprint(WireModel):
    carOrdinal: int | None
    performanceIndex: int | None
    numCylinders: int | None


class ShiftPredictResponse(WireModel):
    """Response shape for GET /api/predict/shift (FR-021)."""

    fingerprint: Fingerprint
    byGear: dict[str, int]
    confidenceByGear: dict[str, float]
    ratios: dict[str, float]
    ratioConfidenceByGear: dict[str, float]
    stage: str
    trainedSampleCount: int
    lastUpdated: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    inputs: list[str]
    modelVersion: str


class ShiftReportPairAgg(WireModel):
    n: int = Field(ge=0)
    avgDeltaRpm: float
    avgEstCostS: float
    direction: Literal["up", "down"]


class ShiftReportResponse(WireModel):
    """Response shape for GET /api/predict/shift/report (FR-022, FR-051).

    v2 additions (FR-051):
    - ``assistInterventionPct``: session-lifetime assist-intervention fraction in
      [0, 1].  Sourced from the live ``ShiftPredictor``'s in-memory session
      counters when ``sessionId=live``; 0.0 for historical sessions because the
      assist counter is not persisted between process restarts.
    - ``byGearPair[*].direction``: "up" for gear_to > gear_from, "down" otherwise.
    """

    sessionId: str
    totalShifts: int = Field(ge=0)
    cleanShifts: int = Field(ge=0)
    avgDeltaRpm: float
    byGearPair: dict[str, ShiftReportPairAgg]
    estTotalCostS: float
    modelVersion: str
    assistInterventionPct: float = Field(ge=0.0, le=1.0)


class ShiftResetRequest(WireModel):
    """POST /api/predict/shift/reset body (FR-023).

    Accepts EITHER explicit (carOrdinal, performanceIndex, numCylinders)
    OR sessionId="live"/<id> to resolve the fingerprint from the live frame.
    """

    sessionId: str | None = None
    carOrdinal: int | None = None
    performanceIndex: int | None = None
    numCylinders: int | None = None


class ShiftResetCounts(WireModel):
    engineCurves: int = Field(ge=0)
    gearRatios: int = Field(ge=0)
    shiftEvents: int = Field(ge=0)
    transmissionModes: int = Field(ge=0)


class ShiftResetResponse(WireModel):
    deleted: ShiftResetCounts
