from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from fh6.infrastructure.db.base import Base


class PredictionModel(Base):
    __tablename__ = "predictions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    predicted_at_session_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    model_version: Mapped[str] = mapped_column(String, nullable=False)
    confidence_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence_tolerance_band: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    inputs: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
