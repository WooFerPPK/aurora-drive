from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from fh6.infrastructure.db.base import Base


class ReplayModel(Base):
    __tablename__ = "replays"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_s: Mapped[float] = mapped_column(Float, nullable=False)
    to_s: Mapped[float] = mapped_column(Float, nullable=False)
    frames: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    annotations: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    tweaks: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(nullable=True)
