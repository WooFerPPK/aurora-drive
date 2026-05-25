from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from fh6.infrastructure.db.base import Base


class DriverProfileModel(Base):
    __tablename__ = "driver_profile"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="local")
    laps_analyzed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    distance_analyzed_m: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    seconds_analyzed: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    fingerprint: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    fingerprint_baseline_90d: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    traits: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    strengths: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    weaknesses: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    car_agnostic_share: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    persona: Mapped[str] = mapped_column(String, nullable=False, default="")
    persona_updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    model_version: Mapped[str] = mapped_column(String, nullable=False, default="placeholder")
