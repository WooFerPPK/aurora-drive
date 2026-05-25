from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fh6.domain.entities.session import (
    Session,
    SessionCloseReason,
    SessionType,
)
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.infrastructure.db.base import rowcount
from fh6.infrastructure.db.models.sessions import SessionModel


class PgSessionRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    @staticmethod
    def _to_domain(row: SessionModel) -> Session:
        return Session(
            id=SessionId(row.id),
            car_id=CarId(row.car_id),
            type=SessionType(row.type),
            started_at=row.started_at,
            ended_at=row.ended_at,
            duration_s=row.duration_s,
            distance_m=row.distance_m,
            top_speed_mps=row.top_speed_mps,
            lap_count=row.lap_count,
            best_lap_s=row.best_lap_s,
            track_id=row.track_id,  # type: ignore[arg-type]
            summary=row.summary,
            style_drift_delta=row.style_drift_delta or {},
            closed_reason=SessionCloseReason(row.closed_reason) if row.closed_reason else None,
            name=row.name,
            bookmarked=row.bookmarked,
        )

    @staticmethod
    def _to_row(session: Session) -> SessionModel:
        return SessionModel(
            id=session.id,
            car_id=session.car_id,
            type=session.type.value,
            started_at=session.started_at,
            ended_at=session.ended_at,
            duration_s=session.duration_s,
            distance_m=session.distance_m,
            top_speed_mps=session.top_speed_mps,
            lap_count=session.lap_count,
            best_lap_s=session.best_lap_s,
            track_id=session.track_id,
            summary=session.summary,
            style_drift_delta=session.style_drift_delta,
            closed_reason=session.closed_reason.value if session.closed_reason else None,
            name=session.name,
            bookmarked=session.bookmarked,
        )

    async def save(self, session: Session) -> None:
        async with self._sm() as db:
            existing = await db.get(SessionModel, session.id)
            if existing is None:
                db.add(self._to_row(session))
            else:
                existing.car_id = session.car_id
                existing.type = session.type.value
                existing.started_at = session.started_at
                existing.ended_at = session.ended_at
                existing.duration_s = session.duration_s
                existing.distance_m = session.distance_m
                existing.top_speed_mps = session.top_speed_mps
                existing.lap_count = session.lap_count
                existing.best_lap_s = session.best_lap_s
                existing.track_id = session.track_id
                existing.summary = session.summary
                existing.style_drift_delta = session.style_drift_delta
                existing.closed_reason = (
                    session.closed_reason.value if session.closed_reason else None
                )
                existing.name = session.name
                existing.bookmarked = session.bookmarked
            await db.commit()

    async def get(self, session_id: SessionId) -> Session | None:
        async with self._sm() as db:
            row = await db.get(SessionModel, session_id)
            return self._to_domain(row) if row else None

    async def latest_in_flight(self) -> Session | None:
        async with self._sm() as db:
            stmt = (
                select(SessionModel)
                .where(SessionModel.ended_at.is_(None))
                .order_by(desc(SessionModel.started_at))
                .limit(1)
            )
            row = (await db.execute(stmt)).scalar_one_or_none()
            return self._to_domain(row) if row else None

    async def list_for_car(self, car_id: CarId, limit: int = 50) -> list[Session]:
        async with self._sm() as db:
            stmt = (
                select(SessionModel)
                .where(SessionModel.car_id == car_id)
                .order_by(
                    desc(SessionModel.bookmarked),
                    desc(SessionModel.started_at),
                )
                .limit(limit)
            )
            rows = (await db.execute(stmt)).scalars().all()
            return [self._to_domain(r) for r in rows]

    async def list_all(self, limit: int = 10_000) -> list[Session]:
        async with self._sm() as db:
            stmt = (
                select(SessionModel)
                .order_by(
                    desc(SessionModel.bookmarked),
                    desc(SessionModel.started_at),
                )
                .limit(limit)
            )
            rows = (await db.execute(stmt)).scalars().all()
            return [self._to_domain(r) for r in rows]

    async def delete(self, session_id: SessionId) -> bool:
        async with self._sm() as db:
            row = await db.get(SessionModel, session_id)
            if row is None:
                return False
            await db.delete(row)
            await db.commit()
            return True

    async def delete_all(self) -> int:
        async with self._sm() as db:
            result = await db.execute(delete(SessionModel))
            await db.commit()
            return rowcount(result)

    async def rename(self, session_id: SessionId, name: str | None) -> Session | None:
        # Empty/whitespace clears to NULL.
        trimmed = name.strip() if name is not None else None
        normalized = trimmed if trimmed else None
        async with self._sm() as db:
            row = await db.get(SessionModel, session_id)
            if row is None:
                return None
            row.name = normalized
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def set_bookmark(self, session_id: SessionId, bookmarked: bool) -> Session | None:
        async with self._sm() as db:
            row = await db.get(SessionModel, session_id)
            if row is None:
                return None
            row.bookmarked = bookmarked
            await db.commit()
            await db.refresh(row)
            return self._to_domain(row)

    async def finalize_stale(
        self,
        *,
        older_than: datetime,
        except_id: SessionId | None,
    ) -> int:
        # Process restarts (and pre-cascade-migration crashes) can leave
        # session rows with ended_at IS NULL forever. The boot-time
        # ResumeSessionOnRestart only handles the latest one, so older
        # corpses accumulate and silently block bulk delete. This sweeps
        # them, skipping the one in-memory SessionManager currently owns.
        conditions = [
            SessionModel.ended_at.is_(None),
            SessionModel.started_at < older_than,
        ]
        if except_id is not None:
            conditions.append(SessionModel.id != except_id)
        stmt = (
            update(SessionModel)
            .where(and_(*conditions))
            .values(
                ended_at=func.now(),
                closed_reason=SessionCloseReason.RESTART_FINALIZE.value,
            )
        )
        async with self._sm() as db:
            result = await db.execute(stmt)
            await db.commit()
            return rowcount(result)
