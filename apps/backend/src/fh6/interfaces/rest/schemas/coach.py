"""Pydantic wire models for `/api/coach` (API spec §7 + Clarification Q3)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from fh6.interfaces.rest.schemas import WireModel


class CoachStatus(WireModel):
    available: bool
    reason: str | None = None
    model: str | None = None


class Citation(WireModel):
    kind: Literal["telemetry_window", "lap_aggregate"]
    sessionId: str
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None
    fields: list[str] | None = None
    sector: int | None = None


class CalloutMessage(WireModel):
    type: Literal["callout"] = "callout"
    id: str
    atS: float
    priority: Literal["tip", "info", "warn"]
    lap: int
    corner: str
    text: str
    cites: list[Citation] = Field(default_factory=list)
    modelVersion: str = ""
    voice: str = "friendly_codriver"


class CoachHello(WireModel):
    type: Literal["hello"] = "hello"
    server: str
    coach: CoachStatus


class CoachAskRequest(WireModel):
    sessionId: str
    question: str


class InsightCard(WireModel):
    id: str
    sessionId: str
    priority: Literal["high", "medium", "low"]
    title: str
    body: str
    tone: Literal["tip", "info", "warn"] = "tip"
    actions: list[str] = Field(default_factory=list)
    deltaIfFixedS: float | None = None
    replayId: str | None = None


class InsightsResponse(WireModel):
    insights: list[InsightCard]


__all__ = [
    "CalloutMessage",
    "Citation",
    "CoachAskRequest",
    "CoachHello",
    "CoachStatus",
    "InsightCard",
    "InsightsResponse",
]
