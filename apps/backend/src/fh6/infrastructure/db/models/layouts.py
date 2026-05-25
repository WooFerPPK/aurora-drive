from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from fh6.infrastructure.db.base import Base


class LayoutModel(Base):
    __tablename__ = "layouts"

    page_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    grid: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    widgets: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
