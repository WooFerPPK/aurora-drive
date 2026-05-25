from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from fh6.infrastructure.db.base import Base


class CarModel(Base):
    __tablename__ = "cars"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    short_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    car_ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    car_class: Mapped[str] = mapped_column(String, nullable=False, default="?")
    performance_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    drivetrain: Mapped[str] = mapped_column(String, nullable=False, default="AWD")
    car_group: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    car_group_label: Mapped[str | None] = mapped_column(String, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(nullable=True)
    session_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_seconds_driven: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
