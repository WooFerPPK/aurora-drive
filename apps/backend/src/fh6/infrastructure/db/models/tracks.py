from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from fh6.infrastructure.db.base import Base


class TrackModel(Base):
    __tablename__ = "tracks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    inferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    confirmed_name: Mapped[str | None] = mapped_column(String, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    outline: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    corners: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime | None] = mapped_column(nullable=True)


class MistakeModel(Base):
    __tablename__ = "mistakes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    car_id: Mapped[str] = mapped_column(ForeignKey("cars.id"), nullable=False, index=True)
    track_id: Mapped[str] = mapped_column(ForeignKey("tracks.id"), nullable=False, index=True)
    pos: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    corner: Mapped[str | None] = mapped_column(String, nullable=True)
    last_observed_at: Mapped[datetime | None] = mapped_column(nullable=True)
