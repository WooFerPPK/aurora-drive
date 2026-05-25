"""Postgres-backed `LayoutsRepository`.

The router stores layouts as opaque `{name, grid, widgets, updatedAt}`
dicts (camelCase `updatedAt`, ISO string). The model has typed columns;
the adapter translates at the boundary so the rest of the stack keeps
the dict-shaped contract `_InMemoryLayoutsRepo` provided.

`patch()` deep-merges only the top-level keys, matching the in-memory
shallow-merge contract; that's enough for the API's current PATCH
shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fh6.infrastructure.db.models.layouts import LayoutModel


class PgLayoutsRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    @staticmethod
    def _to_dict(row: LayoutModel) -> dict[str, Any]:
        return {
            "name": row.name,
            "grid": dict(row.grid or {}),
            "widgets": list(row.widgets or []),
            "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
        }

    @staticmethod
    def _parse_updated_at(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(value)

    async def get(self, page_id: str) -> dict[str, Any] | None:
        async with self._sm() as db:
            row = await db.get(LayoutModel, page_id)
            return self._to_dict(row) if row is not None else None

    async def put(self, page_id: str, layout: dict[str, Any]) -> None:
        async with self._sm() as db:
            row = await db.get(LayoutModel, page_id)
            if row is None:
                row = LayoutModel(page_id=page_id)
                db.add(row)
            row.name = str(layout.get("name", ""))
            row.grid = dict(layout.get("grid", {}))
            row.widgets = list(layout.get("widgets", []))
            row.updated_at = self._parse_updated_at(layout.get("updatedAt"))
            await db.commit()

    async def patch(self, page_id: str, partial: dict[str, Any]) -> dict[str, Any]:
        async with self._sm() as db:
            row = await db.get(LayoutModel, page_id)
            if row is None:
                row = LayoutModel(page_id=page_id)
                db.add(row)
            if "name" in partial:
                row.name = str(partial["name"])
            if "grid" in partial:
                row.grid = dict(partial["grid"])
            if "widgets" in partial:
                row.widgets = list(partial["widgets"])
            if "updatedAt" in partial:
                row.updated_at = self._parse_updated_at(partial["updatedAt"])
            await db.commit()
            await db.refresh(row)
            return self._to_dict(row)
