"""Integration tests for `PgReplayRepository`."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fh6.domain.entities.replay import Replay, ReplayKind
from fh6.domain.value_objects.ids import ReplayId, SessionId
from fh6.infrastructure.db.repositories.replays import PgReplayRepository


@pytest.mark.asyncio
async def test_get_missing_returns_none(
    pg_db: async_sessionmaker[AsyncSession],
) -> None:
    repo = PgReplayRepository(pg_db)
    assert await repo.get(ReplayId("rpl_does_not_exist")) is None


@pytest.mark.asyncio
async def test_save_then_get_telemetry_clip(
    pg_db: async_sessionmaker[AsyncSession], seeded_session_id: str
) -> None:
    repo = PgReplayRepository(pg_db)
    when = datetime.now(UTC).replace(microsecond=0)
    replay = Replay(
        id=ReplayId("rpl_clip_1"),
        kind=ReplayKind.TELEMETRY_CLIP,
        session_id=SessionId(seeded_session_id),
        from_s=10.0,
        to_s=20.0,
        frames=[{"t": 10.0, "x": 1.0}, {"t": 10.1, "x": 1.1}],
        annotations=[{"label": "apex"}],
        created_at=when,
    )

    await repo.save(replay)
    got = await repo.get(ReplayId("rpl_clip_1"))

    assert got == replay


@pytest.mark.asyncio
async def test_save_then_get_counter_factual_round_trips_tweaks(
    pg_db: async_sessionmaker[AsyncSession], seeded_session_id: str
) -> None:
    repo = PgReplayRepository(pg_db)
    replay = Replay(
        id=ReplayId("rpl_cf_1"),
        kind=ReplayKind.COUNTER_FACTUAL,
        session_id=SessionId(seeded_session_id),
        from_s=0.0,
        to_s=5.0,
        frames=[],
        annotations=[],
        tweaks=[{"kind": "brake_point_offset", "delta_m": 5.0}],
    )

    await repo.save(replay)
    got = await repo.get(ReplayId("rpl_cf_1"))

    assert got is not None
    assert got.tweaks == [{"kind": "brake_point_offset", "delta_m": 5.0}]
