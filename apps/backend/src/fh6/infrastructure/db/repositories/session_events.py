"""Postgres adapter for `SessionEventsRepository`.

Persists per-session highlight events for the historical highlight-reel
view (#15). One commit per `save_many` call so a frame producing a batch
of events lands as a single transaction.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fh6.domain.value_objects.session_event import SessionEvent
from fh6.infrastructure.db.models.session_events import SessionEventModel


class PgSessionEventsRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    async def save_many(self, events: list[SessionEvent]) -> None:
        if not events:
            return
        async with self._sm() as db:
            for e in events:
                db.add(
                    SessionEventModel(
                        session_id=e.session_id,
                        at_s=e.at_s,
                        kind=e.kind,
                        payload=dict(e.payload),
                    )
                )
            await db.commit()

    async def list_for_session(self, session_id: str) -> list[SessionEvent]:
        stmt = (
            select(SessionEventModel)
            .where(SessionEventModel.session_id == str(session_id))
            .order_by(SessionEventModel.at_s)
        )
        async with self._sm() as db:
            rows = (await db.execute(stmt)).scalars().all()
        return [
            SessionEvent(
                session_id=r.session_id,
                at_s=r.at_s,
                kind=r.kind,
                payload=dict(r.payload) if r.payload else {},
            )
            for r in rows
        ]
