"""Tests for SessionRepository.finalize_stale via the in-memory fake.

The production Postgres implementation is covered by integration coverage
elsewhere; this exercises the contract that the fake and pg adapter share.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fh6.domain.entities.session import Session, SessionType
from fh6.domain.value_objects.ids import CarId, SessionId
from tests.contract.fake_repos import InMemorySessionRepository


def _open_session(sid: str, started: datetime) -> Session:
    return Session(
        id=SessionId(sid),
        car_id=CarId("car_a"),
        type=SessionType.FREE_ROAM,
        started_at=started,
    )


@pytest.mark.asyncio
async def test_finalize_stale_closes_old_open_sessions() -> None:
    repo = InMemorySessionRepository()
    now = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)
    fresh = _open_session("s_fresh", now - timedelta(seconds=10))
    stale = _open_session("s_stale", now - timedelta(hours=2))
    await repo.save(fresh)
    await repo.save(stale)

    count = await repo.finalize_stale(older_than=now - timedelta(seconds=60), except_id=None)

    assert count == 1
    assert (await repo.get(SessionId("s_stale"))).ended_at is not None
    assert (await repo.get(SessionId("s_fresh"))).ended_at is None


@pytest.mark.asyncio
async def test_finalize_stale_excludes_current_session() -> None:
    repo = InMemorySessionRepository()
    now = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)
    current = _open_session("s_current", now - timedelta(hours=1))
    other = _open_session("s_other", now - timedelta(hours=1))
    await repo.save(current)
    await repo.save(other)

    count = await repo.finalize_stale(
        older_than=now - timedelta(seconds=60),
        except_id=SessionId("s_current"),
    )

    assert count == 1
    assert (await repo.get(SessionId("s_current"))).ended_at is None
    assert (await repo.get(SessionId("s_other"))).ended_at is not None


@pytest.mark.asyncio
async def test_finalize_stale_skips_already_closed() -> None:
    repo = InMemorySessionRepository()
    now = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)
    closed = _open_session("s_closed", now - timedelta(hours=1))
    closed.ended_at = now - timedelta(minutes=30)
    await repo.save(closed)

    count = await repo.finalize_stale(older_than=now - timedelta(seconds=60), except_id=None)

    assert count == 0
