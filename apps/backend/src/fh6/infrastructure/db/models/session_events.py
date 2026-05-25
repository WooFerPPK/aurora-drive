"""SQLAlchemy model for the session_events table.

One row per historical event (lap_completed, sector_completed,
oversteer, off_track, missed_upshift, smashable_hit) produced by
`EventEmitter` during a session. Lifecycle session_started /
session_ended events are not persisted here — they live on the
session row itself.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Float,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from fh6.infrastructure.db.base import Base


class SessionEventModel(Base):
    __tablename__ = "session_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    at_s: Mapped[float] = mapped_column(Float, nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_session_events_session_id_at_s", "session_id", "at_s"),
        Index("ix_session_events_kind", "kind"),
    )
