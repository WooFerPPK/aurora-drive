"""Postgres-backed `MistakesRepository`.

Each Mistake row is one record — the adapter treats `count` as a
literal field, not an aggregation. The mistakes heatmap endpoint
(/api/track/mistakes-heatmap) currently returns no data; the upcoming
detector pipeline will write into this table and the heatmap will read
through this port.

The `id` column is an auto-increment surrogate the domain doesn't care
about. Reads return `Mistake` entities without it; writes ignore any
caller-provided id.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fh6.domain.entities.mistake import Mistake
from fh6.domain.value_objects.ids import CarId, TrackId
from fh6.infrastructure.db.models.tracks import MistakeModel


class PgMistakesRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    @staticmethod
    def _to_domain(row: MistakeModel) -> Mistake:
        return Mistake(
            car_id=CarId(row.car_id),
            track_id=TrackId(row.track_id),
            pos=[float(v) for v in (row.pos or [])],
            kind=row.kind,
            count=row.count,
            corner=row.corner,
            last_observed_at=row.last_observed_at,
        )

    async def save(self, mistake: Mistake) -> None:
        async with self._sm() as db:
            db.add(
                MistakeModel(
                    car_id=str(mistake.car_id),
                    track_id=str(mistake.track_id),
                    pos=list(mistake.pos),
                    kind=mistake.kind,
                    count=mistake.count,
                    corner=mistake.corner,
                    last_observed_at=mistake.last_observed_at,
                )
            )
            await db.commit()

    async def list_for_car_track(self, car_id: CarId, track_id: TrackId) -> list[Mistake]:
        async with self._sm() as db:
            stmt = (
                select(MistakeModel)
                .where(
                    MistakeModel.car_id == str(car_id),
                    MistakeModel.track_id == str(track_id),
                )
                .order_by(MistakeModel.id)
            )
            rows = (await db.execute(stmt)).scalars().all()
            return [self._to_domain(r) for r in rows]
