"""Pydantic wire models for `/api/driver` (API spec §5)."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from fh6.interfaces.rest.schemas import WireModel


class DriverTrait(WireModel):
    id: str
    name: str
    score: float
    blurb: str


class DriverProfileResponse(WireModel):
    lapsAnalyzed: int
    distanceAnalyzedM: float
    secondsAnalyzed: float
    fingerprint: dict[str, float]
    fingerprintBaseline90d: dict[str, float]
    traits: list[DriverTrait]
    strengths: list[str]
    weaknesses: list[str]
    carAgnosticShare: float
    persona: str
    personaUpdatedAt: datetime | None = None
    modelVersion: str


class SessionClusterPoint(WireModel):
    sessionId: str
    fingerprint: dict[str, float]


class DriverEvolutionResponse(WireModel):
    days: int
    # Per-trait time series. Each value is a list of [unix_timestamp_s, value]
    # pairs. Keys are trait ids (smooth, brave, early, patient, precise, consist).
    series: dict[str, list[list[float]]]
    sessionClusters: list[SessionClusterPoint] = Field(default_factory=list)
