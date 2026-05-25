from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from fh6.infrastructure.db.base import Base


class CoachCalloutModel(Base):
    __tablename__ = "coach_callouts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    at_session_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    priority: Mapped[str] = mapped_column(String, nullable=False)
    lap_context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    text: Mapped[str] = mapped_column(String, nullable=False)
    cites: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    model_version: Mapped[str] = mapped_column(String, nullable=False, default="")
    voice: Mapped[str] = mapped_column(String, nullable=False, default="friendly_codriver")


class CoachInsightModel(Base):
    __tablename__ = "coach_insights"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    priority: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(String, nullable=False, default="")
    tone: Mapped[str] = mapped_column(String, nullable=False)
    actions: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    delta_if_fixed_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    replay_id: Mapped[str | None] = mapped_column(String, nullable=True)
