from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class DriverProfile:
    laps_analyzed: int = 0
    distance_analyzed_m: float = 0.0
    seconds_analyzed: float = 0.0
    fingerprint: dict[str, float] = field(default_factory=dict)
    fingerprint_baseline_90d: dict[str, float] = field(default_factory=dict)
    traits: list[dict[str, Any]] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    car_agnostic_share: float = 0.0
    persona: str = ""
    persona_updated_at: datetime | None = None
    model_version: str = "placeholder"
