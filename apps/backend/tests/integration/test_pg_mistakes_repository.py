"""Integration tests for `PgMistakesRepository`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fh6.domain.entities.mistake import Mistake
from fh6.domain.entities.track import Track
from fh6.domain.value_objects.ids import CarId, TrackId
from fh6.infrastructure.db.repositories.mistakes import PgMistakesRepository
from fh6.infrastructure.db.repositories.tracks import PgTrackRepository


@pytest.fixture
async def seeded_track_id(
    pg_db: async_sessionmaker[AsyncSession],
) -> str:
    track_id = "trk_test"
    await PgTrackRepository(pg_db).save(Track(id=TrackId(track_id), display_name="Test Track"))
    return track_id


@pytest.mark.asyncio
async def test_list_empty_for_unknown_car_track(
    pg_db: async_sessionmaker[AsyncSession],
) -> None:
    repo = PgMistakesRepository(pg_db)
    got = await repo.list_for_car_track(CarId("none"), TrackId("none"))
    assert got == []


@pytest.mark.asyncio
async def test_save_then_list_for_car_track(
    pg_db: async_sessionmaker[AsyncSession],
    seeded_session_id: str,
    seeded_track_id: str,
) -> None:
    repo = PgMistakesRepository(pg_db)
    when = datetime.now(UTC).replace(microsecond=0)
    mistake = Mistake(
        car_id=CarId("car_test_0001"),
        track_id=TrackId(seeded_track_id),
        pos=[100.5, -50.2],
        kind="late_brake",
        count=3,
        corner="T1",
        last_observed_at=when,
    )
    await repo.save(mistake)

    got = await repo.list_for_car_track(CarId("car_test_0001"), TrackId(seeded_track_id))
    assert got == [mistake]


@pytest.mark.asyncio
async def test_list_filters_by_car_and_track(
    pg_db: async_sessionmaker[AsyncSession],
    seeded_session_id: str,
    seeded_track_id: str,
) -> None:
    repo = PgMistakesRepository(pg_db)
    car = CarId("car_test_0001")
    other_track = "trk_other"
    await PgTrackRepository(pg_db).save(Track(id=TrackId(other_track), display_name="Other"))

    await repo.save(
        Mistake(car_id=car, track_id=TrackId(seeded_track_id), pos=[1.0, 1.0], kind="a")
    )
    await repo.save(Mistake(car_id=car, track_id=TrackId(other_track), pos=[2.0, 2.0], kind="b"))

    got = await repo.list_for_car_track(car, TrackId(seeded_track_id))
    assert [m.kind for m in got] == ["a"]
