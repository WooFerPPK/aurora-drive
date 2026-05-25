"""Integration tests for `PgLayoutsRepository`."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fh6.infrastructure.db.repositories.layouts import PgLayoutsRepository


def _layout(*, name: str = "live", widgets: list | None = None) -> dict:
    return {
        "name": name,
        "grid": {"columns": 12, "rows": 8},
        "widgets": widgets
        if widgets is not None
        else [{"id": "w1", "kind": "current_lap", "x": 0, "y": 0, "w": 4, "h": 2}],
        "updatedAt": "2026-05-24T12:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_get_missing_returns_none(
    pg_db: async_sessionmaker[AsyncSession],
) -> None:
    repo = PgLayoutsRepository(pg_db)
    assert await repo.get("live") is None


@pytest.mark.asyncio
async def test_put_then_get_round_trips(
    pg_db: async_sessionmaker[AsyncSession],
) -> None:
    repo = PgLayoutsRepository(pg_db)
    layout = _layout(name="live default")
    await repo.put("live", layout)
    got = await repo.get("live")
    assert got == layout


@pytest.mark.asyncio
async def test_put_overwrites_existing(
    pg_db: async_sessionmaker[AsyncSession],
) -> None:
    repo = PgLayoutsRepository(pg_db)
    await repo.put("live", _layout(name="first"))
    await repo.put("live", _layout(name="second"))
    got = await repo.get("live")
    assert got is not None
    assert got["name"] == "second"


@pytest.mark.asyncio
async def test_patch_merges_partial_and_preserves_other_keys(
    pg_db: async_sessionmaker[AsyncSession],
) -> None:
    repo = PgLayoutsRepository(pg_db)
    await repo.put("live", _layout(name="original"))
    merged = await repo.patch("live", {"name": "renamed"})

    assert merged["name"] == "renamed"
    # other fields untouched
    assert merged["grid"] == {"columns": 12, "rows": 8}
    assert merged["widgets"][0]["id"] == "w1"


@pytest.mark.asyncio
async def test_patch_creates_row_when_absent(
    pg_db: async_sessionmaker[AsyncSession],
) -> None:
    repo = PgLayoutsRepository(pg_db)
    merged = await repo.patch("coach", {"name": "new"})
    assert merged["name"] == "new"
    assert await repo.get("coach") is not None
