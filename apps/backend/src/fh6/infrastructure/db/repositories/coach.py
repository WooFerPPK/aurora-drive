"""Postgres-backed `CoachRepository`.

Persists callouts and insights for `/api/coach/*` and the coach WS push
channel. `dismiss_insight` uses a conditional UPDATE so callers learn
whether the insight transitioned (returns True) or was already dismissed
(returns False) — matching the in-memory contract `_InMemoryCoachRepository`
used to provide.

Replaces the boot-time fallback in `interfaces/app.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fh6.domain.entities.coach_callout import CalloutPriority, CoachCallout
from fh6.domain.entities.coach_insight import CoachInsight
from fh6.domain.value_objects.ids import ReplayId, SessionId
from fh6.infrastructure.db.base import rowcount
from fh6.infrastructure.db.models.coach import CoachCalloutModel, CoachInsightModel


class PgCoachRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    @staticmethod
    def _callout_to_row(c: CoachCallout) -> CoachCalloutModel:
        return CoachCalloutModel(
            id=c.id,
            session_id=str(c.session_id),
            at_session_seconds=c.at_session_seconds,
            priority=c.priority.value,
            lap_context=dict(c.lap_context),
            text=c.text,
            cites=list(c.cites),
            model_version=c.model_version,
            voice=c.voice,
        )

    @staticmethod
    def _callout_to_domain(row: CoachCalloutModel) -> CoachCallout:
        return CoachCallout(
            id=row.id,
            session_id=SessionId(row.session_id),
            at_session_seconds=row.at_session_seconds,
            priority=CalloutPriority(row.priority),
            lap_context=dict(row.lap_context or {}),
            text=row.text,
            cites=list(row.cites or []),
            model_version=row.model_version,
            voice=row.voice,
        )

    @staticmethod
    def _insight_to_row(i: CoachInsight) -> CoachInsightModel:
        return CoachInsightModel(
            id=i.id,
            session_id=str(i.session_id),
            priority=i.priority,
            title=i.title,
            body=i.body,
            tone=i.tone,
            actions=list(i.actions),
            delta_if_fixed_s=i.delta_if_fixed_s,
            dismissed_at=i.dismissed_at,
            replay_id=str(i.replay_id) if i.replay_id is not None else None,
        )

    @staticmethod
    def _insight_to_domain(row: CoachInsightModel) -> CoachInsight:
        return CoachInsight(
            id=row.id,
            session_id=SessionId(row.session_id),
            priority=row.priority,
            title=row.title,
            body=row.body,
            tone=row.tone,
            actions=list(row.actions or []),
            delta_if_fixed_s=row.delta_if_fixed_s,
            dismissed_at=row.dismissed_at,
            replay_id=ReplayId(row.replay_id) if row.replay_id is not None else None,
        )

    async def save_callout(self, callout: CoachCallout) -> None:
        async with self._sm() as db:
            db.add(self._callout_to_row(callout))
            await db.commit()

    async def list_callouts(self, session_id: SessionId) -> list[CoachCallout]:
        async with self._sm() as db:
            stmt = (
                select(CoachCalloutModel)
                .where(CoachCalloutModel.session_id == str(session_id))
                .order_by(CoachCalloutModel.at_session_seconds, CoachCalloutModel.id)
            )
            rows = (await db.execute(stmt)).scalars().all()
            return [self._callout_to_domain(r) for r in rows]

    async def save_insight(self, insight: CoachInsight) -> None:
        async with self._sm() as db:
            db.add(self._insight_to_row(insight))
            await db.commit()

    async def list_insights(self, session_id: SessionId) -> list[CoachInsight]:
        async with self._sm() as db:
            stmt = (
                select(CoachInsightModel)
                .where(
                    CoachInsightModel.session_id == str(session_id),
                    CoachInsightModel.dismissed_at.is_(None),
                )
                .order_by(CoachInsightModel.id)
            )
            rows = (await db.execute(stmt)).scalars().all()
            return [self._insight_to_domain(r) for r in rows]

    async def get_insight(self, insight_id: str) -> CoachInsight | None:
        async with self._sm() as db:
            row = await db.get(CoachInsightModel, insight_id)
            return self._insight_to_domain(row) if row is not None else None

    async def dismiss_insight(self, insight_id: str) -> bool:
        async with self._sm() as db:
            stmt = (
                update(CoachInsightModel)
                .where(
                    CoachInsightModel.id == insight_id,
                    CoachInsightModel.dismissed_at.is_(None),
                )
                .values(dismissed_at=datetime.now(UTC))
            )
            result = await db.execute(stmt)
            await db.commit()
            return rowcount(result) > 0
