from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, ForeignKey, Integer, PrimaryKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column

from fh6.infrastructure.db.base import Base


class FrameModel(Base):
    """The hypertable. Time-partitioned by `time`. Migration adds the
    Timescale hypertable and continuous aggregates frames_30hz / frames_10hz.
    """

    __tablename__ = "frames"
    __table_args__ = (PrimaryKeyConstraint("session_id", "time"),)

    time: Mapped[datetime] = mapped_column(nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    car_id: Mapped[str] = mapped_column(ForeignKey("cars.id"), nullable=False, index=True)

    packet_timestamp_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_race_on: Mapped[bool] = mapped_column(Boolean, nullable=False)

    race: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    engine: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    drivetrain: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    motion: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    wheels: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    world: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    derived: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    modeled: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    tail_reserved_byte: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
