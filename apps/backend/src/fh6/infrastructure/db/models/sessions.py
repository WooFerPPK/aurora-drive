from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from fh6.infrastructure.db.base import Base


class SessionModel(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    car_id: Mapped[str] = mapped_column(ForeignKey("cars.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String, nullable=False, default="free_roam")
    started_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_m: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    top_speed_mps: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    lap_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_lap_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    track_id: Mapped[str | None] = mapped_column(String, nullable=True)
    summary: Mapped[str] = mapped_column(String, nullable=False, default="")
    style_drift_delta: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    closed_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    bookmarked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class SessionLapModel(Base):
    """Per-lap timing records. UNIQUE(session_id, lap_number) enables upsert
    so a rewound lap overwrites the provisional time instead of duplicating."""

    __tablename__ = "session_laps"
    __table_args__ = (
        UniqueConstraint("session_id", "lap_number", name="uq_session_laps_session_lap"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lap_number: Mapped[int] = mapped_column(Integer, nullable=False)
    lap_time_s: Mapped[float] = mapped_column(Float, nullable=False)
