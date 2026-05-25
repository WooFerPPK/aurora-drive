"""Integration tests for `PgCoachRepository` against a real Postgres."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fh6.domain.entities.coach_callout import CalloutPriority, CoachCallout
from fh6.domain.entities.coach_insight import CoachInsight
from fh6.domain.value_objects.ids import SessionId
from fh6.infrastructure.db.repositories.coach import PgCoachRepository


def _callout(
    *, id: str, session_id: str, at: float, priority: CalloutPriority = CalloutPriority.TIP
) -> CoachCallout:
    return CoachCallout(
        id=id,
        session_id=SessionId(session_id),
        at_session_seconds=at,
        priority=priority,
        lap_context={"lap": 1},
        text="hello",
        cites=[{"k": "v"}],
        model_version="m-1",
    )


def _insight(*, id: str, session_id: str, title: str = "t") -> CoachInsight:
    return CoachInsight(
        id=id,
        session_id=SessionId(session_id),
        priority="high",
        title=title,
        body="b",
        tone="tip",
        actions=["a1", "a2"],
        delta_if_fixed_s=0.25,
    )


@pytest.mark.asyncio
async def test_save_and_list_callouts_in_timeline_order(
    pg_db: async_sessionmaker[AsyncSession], seeded_session_id: str
) -> None:
    repo = PgCoachRepository(pg_db)
    await repo.save_callout(_callout(id="c2", session_id=seeded_session_id, at=2.0))
    await repo.save_callout(_callout(id="c1", session_id=seeded_session_id, at=1.0))
    await repo.save_callout(_callout(id="c3", session_id=seeded_session_id, at=3.0))

    got = await repo.list_callouts(SessionId(seeded_session_id))

    assert [c.id for c in got] == ["c1", "c2", "c3"]
    assert got[0].priority is CalloutPriority.TIP
    assert got[0].lap_context == {"lap": 1}
    assert got[0].cites == [{"k": "v"}]


@pytest.mark.asyncio
async def test_list_callouts_empty_for_unknown_session(
    pg_db: async_sessionmaker[AsyncSession],
) -> None:
    repo = PgCoachRepository(pg_db)
    assert await repo.list_callouts(SessionId("ses_does_not_exist")) == []


@pytest.mark.asyncio
async def test_save_and_list_insights_excludes_dismissed(
    pg_db: async_sessionmaker[AsyncSession], seeded_session_id: str
) -> None:
    repo = PgCoachRepository(pg_db)
    await repo.save_insight(_insight(id="i1", session_id=seeded_session_id, title="one"))
    await repo.save_insight(_insight(id="i2", session_id=seeded_session_id, title="two"))
    await repo.save_insight(_insight(id="i3", session_id=seeded_session_id, title="three"))

    assert await repo.dismiss_insight("i2") is True

    got = await repo.list_insights(SessionId(seeded_session_id))
    assert [i.id for i in got] == ["i1", "i3"]


@pytest.mark.asyncio
async def test_dismiss_insight_returns_false_when_already_dismissed(
    pg_db: async_sessionmaker[AsyncSession], seeded_session_id: str
) -> None:
    repo = PgCoachRepository(pg_db)
    await repo.save_insight(_insight(id="i1", session_id=seeded_session_id))

    assert await repo.dismiss_insight("i1") is True
    assert await repo.dismiss_insight("i1") is False


@pytest.mark.asyncio
async def test_dismiss_insight_returns_false_when_not_found(
    pg_db: async_sessionmaker[AsyncSession],
) -> None:
    repo = PgCoachRepository(pg_db)
    assert await repo.dismiss_insight("unknown") is False


@pytest.mark.asyncio
async def test_get_insight_returns_row_or_none(
    pg_db: async_sessionmaker[AsyncSession], seeded_session_id: str
) -> None:
    repo = PgCoachRepository(pg_db)
    await repo.save_insight(_insight(id="i_target", session_id=seeded_session_id, title="t"))

    got = await repo.get_insight("i_target")
    assert got is not None
    assert got.id == "i_target"
    assert got.title == "t"
    assert await repo.get_insight("not_there") is None


@pytest.mark.asyncio
async def test_get_insight_returns_dismissed_row(
    pg_db: async_sessionmaker[AsyncSession], seeded_session_id: str
) -> None:
    # get_insight does NOT filter dismissed insights — replay_insight needs
    # to recover the citation window even after dismissal.
    repo = PgCoachRepository(pg_db)
    await repo.save_insight(_insight(id="i_dismissed", session_id=seeded_session_id))
    await repo.dismiss_insight("i_dismissed")

    got = await repo.get_insight("i_dismissed")
    assert got is not None
    assert got.dismissed_at is not None
