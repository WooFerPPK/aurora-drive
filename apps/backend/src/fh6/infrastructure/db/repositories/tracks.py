"""Postgres-backed `TrackRepository`.

The `tracks` table has existed since the initial schema but had no
adapter or boot-time fallback — the only current reader is
`track_inference.cluster.open_world_default()`, which returns a
hardcoded MVP default and ignores persistence entirely. This adapter
lands the missing port and adapter so the upcoming track-confirmation
flow (post-MVP) has somewhere to persist learned tracks. Not wired
into the lifespan yet; consumer arrives in a later phase.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fh6.domain.entities.track import Track
from fh6.domain.value_objects.ids import TrackId
from fh6.infrastructure.db.models.tracks import TrackModel


class PgTrackRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    @staticmethod
    def _to_domain(row: TrackModel) -> Track:
        outline: list[tuple[float, float]] = [
            (float(p[0]), float(p[1])) for p in (row.outline or [])
        ]
        return Track(
            id=TrackId(row.id),
            display_name=row.display_name,
            inferred=row.inferred,
            confirmed_name=row.confirmed_name,
            confirmed_at=row.confirmed_at,
            outline=outline,
            corners=list(row.corners or []),
            created_at=row.created_at,
        )

    @staticmethod
    def _to_row(track: Track) -> TrackModel:
        return TrackModel(
            id=str(track.id),
            display_name=track.display_name,
            inferred=track.inferred,
            confirmed_name=track.confirmed_name,
            confirmed_at=track.confirmed_at,
            outline=[list(p) for p in track.outline],
            corners=list(track.corners),
            created_at=track.created_at,
        )

    async def get(self, track_id: TrackId) -> Track | None:
        async with self._sm() as db:
            row = await db.get(TrackModel, str(track_id))
            return self._to_domain(row) if row is not None else None

    async def save(self, track: Track) -> None:
        async with self._sm() as db:
            row = await db.get(TrackModel, str(track.id))
            if row is None:
                db.add(self._to_row(track))
            else:
                row.display_name = track.display_name
                row.inferred = track.inferred
                row.confirmed_name = track.confirmed_name
                row.confirmed_at = track.confirmed_at
                row.outline = [list(p) for p in track.outline]
                row.corners = list(track.corners)
                row.created_at = track.created_at
            await db.commit()

    async def list_all(self) -> list[Track]:
        async with self._sm() as db:
            rows = (await db.execute(select(TrackModel).order_by(TrackModel.id))).scalars().all()
            return [self._to_domain(r) for r in rows]
