"""Integration tests for `PgTrackRepository`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fh6.domain.entities.track import Track
from fh6.domain.value_objects.ids import TrackId
from fh6.infrastructure.db.repositories.tracks import PgTrackRepository


def _track(*, id: str = "trk_open_world", name: str = "Open World") -> Track:
    return Track(
        id=TrackId(id),
        display_name=name,
        inferred=True,
        outline=[(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)],
        corners=[{"index": 1, "label": "T1"}],
        created_at=datetime.now(UTC).replace(microsecond=0),
    )


@pytest.mark.asyncio
async def test_get_missing_returns_none(
    pg_db: async_sessionmaker[AsyncSession],
) -> None:
    repo = PgTrackRepository(pg_db)
    assert await repo.get(TrackId("trk_none")) is None


@pytest.mark.asyncio
async def test_save_then_get_round_trips(
    pg_db: async_sessionmaker[AsyncSession],
) -> None:
    repo = PgTrackRepository(pg_db)
    track = _track()
    await repo.save(track)
    got = await repo.get(TrackId("trk_open_world"))
    assert got == track


@pytest.mark.asyncio
async def test_save_overwrites_existing(
    pg_db: async_sessionmaker[AsyncSession],
) -> None:
    repo = PgTrackRepository(pg_db)
    await repo.save(_track(name="first"))
    await repo.save(_track(name="second"))
    got = await repo.get(TrackId("trk_open_world"))
    assert got is not None
    assert got.display_name == "second"


@pytest.mark.asyncio
async def test_save_records_confirmation(
    pg_db: async_sessionmaker[AsyncSession],
) -> None:
    repo = PgTrackRepository(pg_db)
    when = datetime.now(UTC).replace(microsecond=0)
    track = Track(
        id=TrackId("trk_silverstone"),
        display_name="Silverstone (inferred)",
        inferred=False,
        confirmed_name="Silverstone",
        confirmed_at=when,
    )
    await repo.save(track)
    got = await repo.get(TrackId("trk_silverstone"))
    assert got is not None
    assert got.confirmed_name == "Silverstone"
    assert got.confirmed_at == when
    assert got.inferred is False


@pytest.mark.asyncio
async def test_list_all_orders_by_id(
    pg_db: async_sessionmaker[AsyncSession],
) -> None:
    repo = PgTrackRepository(pg_db)
    await repo.save(_track(id="trk_b", name="B"))
    await repo.save(_track(id="trk_a", name="A"))
    got = await repo.list_all()
    assert [t.id for t in got] == [TrackId("trk_a"), TrackId("trk_b")]
