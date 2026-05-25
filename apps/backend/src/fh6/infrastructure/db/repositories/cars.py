from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fh6.domain.entities.car import Car
from fh6.domain.value_objects.ids import CarId
from fh6.infrastructure.db.base import rowcount
from fh6.infrastructure.db.models.cars import CarModel
from fh6.infrastructure.db.models.sessions import SessionModel


class PgCarRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    @staticmethod
    def _to_domain(row: CarModel) -> Car:
        return Car(
            id=CarId(row.id),
            display_name=row.display_name,
            short_name=row.short_name,
            car_ordinal=row.car_ordinal,
            car_class=row.car_class,
            performance_index=row.performance_index,
            drivetrain=row.drivetrain,
            car_group=row.car_group,
            car_group_label=row.car_group_label,
            last_seen_at=row.last_seen_at,
            session_count=row.session_count,
            total_seconds_driven=row.total_seconds_driven,
        )

    async def upsert(self, car: Car) -> None:
        async with self._sm() as db:
            existing = await db.get(CarModel, car.id)
            if existing is None:
                db.add(
                    CarModel(
                        id=car.id,
                        display_name=car.display_name,
                        short_name=car.short_name,
                        car_ordinal=car.car_ordinal,
                        car_class=car.car_class,
                        performance_index=car.performance_index,
                        drivetrain=car.drivetrain,
                        car_group=car.car_group,
                        car_group_label=car.car_group_label,
                        last_seen_at=car.last_seen_at,
                        session_count=car.session_count,
                        total_seconds_driven=car.total_seconds_driven,
                    )
                )
            else:
                # display_name / short_name are user-curatable via
                # PATCH /api/cars/{ordinal} — the DB row wins over the
                # ordinal_lookup seed once written, so we never let a
                # later ingest clobber a name a user fixed.
                existing.car_class = car.car_class
                existing.performance_index = car.performance_index
                existing.drivetrain = car.drivetrain
                existing.car_group = car.car_group
                existing.car_group_label = car.car_group_label
                existing.last_seen_at = car.last_seen_at
                existing.session_count = car.session_count
                existing.total_seconds_driven = car.total_seconds_driven
            await db.commit()

    async def get(self, car_id: CarId) -> Car | None:
        async with self._sm() as db:
            row = await db.get(CarModel, car_id)
            return self._to_domain(row) if row else None

    async def list_all(self) -> list[Car]:
        async with self._sm() as db:
            rows = (await db.execute(select(CarModel))).scalars().all()
            return [self._to_domain(r) for r in rows]

    async def delete_all_sessions(self, car_id: CarId) -> int:
        async with self._sm() as db:
            stmt = delete(SessionModel).where(SessionModel.car_id == car_id)
            result = await db.execute(stmt)
            await db.commit()
            return rowcount(result)

    async def delete(self, car_id: CarId) -> bool:
        # Sessions, frames, mistakes cascade via the FK constraints set
        # up in migration 0003_car_fks_cascade.
        async with self._sm() as db:
            row = await db.get(CarModel, car_id)
            if row is None:
                return False
            await db.delete(row)
            await db.commit()
            return True

    async def delete_all(self) -> int:
        async with self._sm() as db:
            result = await db.execute(delete(CarModel))
            await db.commit()
            return rowcount(result)

    async def rename_by_ordinal(self, ordinal: int, *, display_name: str, short_name: str) -> int:
        async with self._sm() as db:
            stmt = select(CarModel).where(CarModel.car_ordinal == ordinal)
            rows = (await db.execute(stmt)).scalars().all()
            for row in rows:
                row.display_name = display_name
                row.short_name = short_name
            await db.commit()
            return len(rows)
