"""Integration tests for `PgDriverRepository`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fh6.domain.entities.driver_profile import DriverProfile
from fh6.infrastructure.db.repositories.driver import PgDriverRepository


@pytest.mark.asyncio
async def test_get_returns_empty_profile_when_row_absent(
    pg_db: async_sessionmaker[AsyncSession],
) -> None:
    repo = PgDriverRepository(pg_db)
    got = await repo.get()
    assert got == DriverProfile()


@pytest.mark.asyncio
async def test_save_then_get_round_trips_all_fields(
    pg_db: async_sessionmaker[AsyncSession],
) -> None:
    repo = PgDriverRepository(pg_db)
    when = datetime.now(UTC).replace(microsecond=0)
    profile = DriverProfile(
        laps_analyzed=42,
        distance_analyzed_m=12_345.67,
        seconds_analyzed=987.6,
        fingerprint={"throttle_smoothness": 0.81},
        fingerprint_baseline_90d={"throttle_smoothness": 0.79},
        traits=[{"name": "smooth"}],
        strengths=["braking"],
        weaknesses=["exit_speed"],
        car_agnostic_share=0.62,
        persona="The Smoothie",
        persona_updated_at=when,
        model_version="v1.2",
    )

    await repo.save(profile)
    got = await repo.get()

    assert got == profile


@pytest.mark.asyncio
async def test_save_overwrites_existing_row(
    pg_db: async_sessionmaker[AsyncSession],
) -> None:
    repo = PgDriverRepository(pg_db)
    await repo.save(DriverProfile(laps_analyzed=1))
    await repo.save(DriverProfile(laps_analyzed=2, persona="updated"))

    got = await repo.get()
    assert got.laps_analyzed == 2
    assert got.persona == "updated"
