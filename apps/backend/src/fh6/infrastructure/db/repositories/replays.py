"""Postgres-backed `ReplayRepository`.

Replays are immutable — `save()` inserts a new row; `get()` fetches by
ULID. `ReplayKind.COUNTER_FACTUAL` requires `tweaks`, but that
invariant is enforced at the domain edge (`Replay.__post_init__`), so
this adapter is a thin translation layer.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fh6.domain.entities.replay import Replay, ReplayKind
from fh6.domain.value_objects.ids import ReplayId, SessionId
from fh6.infrastructure.db.models.replays import ReplayModel


class PgReplayRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    @staticmethod
    def _to_row(replay: Replay) -> ReplayModel:
        return ReplayModel(
            id=str(replay.id),
            kind=replay.kind.value,
            session_id=str(replay.session_id),
            from_s=replay.from_s,
            to_s=replay.to_s,
            frames=list(replay.frames),
            annotations=list(replay.annotations),
            tweaks=list(replay.tweaks) if replay.tweaks is not None else None,
            created_at=replay.created_at,
        )

    @staticmethod
    def _to_domain(row: ReplayModel) -> Replay:
        return Replay(
            id=ReplayId(row.id),
            kind=ReplayKind(row.kind),
            session_id=SessionId(row.session_id),
            from_s=row.from_s,
            to_s=row.to_s,
            frames=list(row.frames or []),
            annotations=list(row.annotations or []),
            tweaks=list(row.tweaks) if row.tweaks is not None else None,
            created_at=row.created_at,
        )

    async def save(self, replay: Replay) -> None:
        async with self._sm() as db:
            db.add(self._to_row(replay))
            await db.commit()

    async def get(self, replay_id: ReplayId) -> Replay | None:
        async with self._sm() as db:
            row = await db.get(ReplayModel, str(replay_id))
            return self._to_domain(row) if row is not None else None
