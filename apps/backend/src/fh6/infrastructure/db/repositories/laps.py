from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fh6.domain.value_objects.completed_lap import CompletedLap
from fh6.domain.value_objects.ids import SessionId
from fh6.infrastructure.db.models.sessions import SessionLapModel


class PgLapRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    async def upsert_lap(self, session_id: SessionId, lap: CompletedLap) -> None:
        stmt = (
            pg_insert(SessionLapModel)
            .values(
                session_id=str(session_id),
                lap_number=lap.lap_number,
                lap_time_s=lap.lap_time_s,
            )
            .on_conflict_do_update(
                constraint="uq_session_laps_session_lap",
                set_={"lap_time_s": lap.lap_time_s},
            )
        )
        async with self._sm() as db:
            await db.execute(stmt)
            await db.commit()

    async def list_laps_for_session(self, session_id: SessionId) -> list[CompletedLap]:
        stmt = (
            select(SessionLapModel)
            .where(SessionLapModel.session_id == str(session_id))
            .order_by(SessionLapModel.lap_number)
        )
        async with self._sm() as db:
            rows = (await db.execute(stmt)).scalars().all()
        return [CompletedLap(lap_number=r.lap_number, lap_time_s=r.lap_time_s) for r in rows]

    async def min_lap_time_for_session(self, session_id: SessionId) -> float | None:
        laps = await self.list_laps_for_session(session_id)
        if not laps:
            return None
        return min(lap.lap_time_s for lap in laps)
