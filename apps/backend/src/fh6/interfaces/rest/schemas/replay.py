"""Pydantic wire models for `/api/replay` (API spec §9)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from fh6.interfaces.rest.schemas import WireModel


class ReplayResponse(WireModel):
    id: str
    kind: Literal["counter_factual", "telemetry_clip"]
    sessionId: str
    fromS: float = Field(serialization_alias="from")
    toS: float = Field(serialization_alias="to")
    frames: list[list[Any]] = Field(default_factory=list)
    annotations: list[dict[str, Any]] = Field(default_factory=list)
    tweaks: list[dict[str, Any]] | None = None
    createdAt: datetime | None = None
