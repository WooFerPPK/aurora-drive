"""TimescaleFrameStore: TimescaleDB-backed implementation of FrameStore.

Read paths:

  - hz=30: reads the `frames_30hz` continuous aggregate (the authoritative
    30 Hz view per the plan).
  - hz=10 and hz=60: reads the source `frames` hypertable. The 10 Hz CAGG
    exists but its alignment vs the base table is unverified, so the
    safer choice is to read base and decimate in Python until we have a
    drift check (Risk #1 in the refactor plan).

Writes always go to the source hypertable (constitution Principle VIII —
no write-time decimation).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Literal

from sqlalchemy import bindparam, delete, desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fh6.domain.entities.frame import DecodedFrame
from fh6.domain.ports.frame_store import FrameStore
from fh6.domain.value_objects.frame_position import FramePositionSnapshot
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.infrastructure.db.base import rowcount
from fh6.infrastructure.db.models.frames import FrameModel


def _table_for_hz(hz: int) -> str:
    if hz == 60:
        return "frames"
    if hz == 30:
        return "frames_30hz"
    if hz == 10:
        return "frames_10hz"
    raise ValueError(f"unsupported hz: {hz}")


class TimescaleFrameStore(FrameStore):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    @staticmethod
    def _to_row(frame: DecodedFrame) -> FrameModel:
        if frame.session_id is None:
            raise ValueError("cannot persist a frame with no session_id")
        modeled = {
            "tireWear": frame.modeled.tire_wear,
            "tireWearConfidence": frame.modeled.tire_wear_confidence.value,
            "tireWearToleranceBand": frame.modeled.tire_wear_confidence.tolerance_band,
            "modeledByVersion": frame.modeled.tire_wear_confidence.model_version,
            **frame.modeled.extras,
        }
        derived = {
            "balance": frame.derived.balance,
            "weightFront": frame.derived.weight_front,
            "weightLeft": frame.derived.weight_left,
            "bodyControl": frame.derived.body_control,
            "gripBudgetUsed": frame.derived.grip_budget_used,
            "powerBandOccupancy": frame.derived.power_band_occupancy,
            "throttleSmoothness": frame.derived.throttle_smoothness,
        }
        return FrameModel(
            time=frame.received_at,
            session_id=frame.session_id,
            car_id=frame.car_id,
            packet_timestamp_ms=frame.raw.timestamp_ms,
            is_race_on=frame.raw.is_race_on,
            race=frame.raw.race,
            engine=frame.raw.engine,
            drivetrain=frame.raw.drivetrain,
            motion=frame.raw.motion,
            inputs=frame.raw.inputs,
            wheels=frame.raw.wheels,
            world=frame.raw.world,
            derived=derived,
            modeled=modeled,
            tail_reserved_byte=frame.raw.tail_reserved_byte,
        )

    async def append(self, frame: DecodedFrame) -> None:
        async with self._sm() as db:
            db.add(self._to_row(frame))
            await db.commit()

    async def append_batch(self, frames: Sequence[DecodedFrame]) -> None:
        if not frames:
            return
        async with self._sm() as db:
            for f in frames:
                db.add(self._to_row(f))
            await db.commit()

    async def _read_rows(self, session_id: SessionId, *, hz: Literal[10, 30, 60]) -> list[Any]:
        """Read decimated frames ordered by time.

        hz=30 reads `frames_30hz` (CAGG) via raw SQL — the CAGG drops the
        `drivetrain` column, so the returned rows expose it as None and
        any caller that needs gear info must read at 60 Hz.
        hz=10 and hz=60 read the base `frames` hypertable via the ORM.
        """
        if hz == 30:
            stmt = text(
                "SELECT bucket AS time, is_race_on, race, engine, motion, "
                "inputs, wheels, derived, modeled "
                "FROM frames_30hz "
                "WHERE session_id = :session_id "
                "ORDER BY bucket"
            ).bindparams(bindparam("session_id", value=session_id))
            async with self._sm() as db:
                result = await db.execute(stmt)
                return [
                    SimpleNamespace(
                        time=m["time"],
                        is_race_on=m["is_race_on"],
                        race=m["race"],
                        engine=m["engine"],
                        motion=m["motion"],
                        inputs=m["inputs"],
                        wheels=m["wheels"],
                        derived=m["derived"],
                        modeled=m["modeled"],
                        drivetrain=None,
                    )
                    for m in result.mappings().all()
                ]
        # 10 Hz: CAGG exists but alignment isn't verified yet (Risk #1).
        # 60 Hz: always reads the source hypertable.
        async with self._sm() as db:
            ormstmt = (
                select(FrameModel)
                .where(FrameModel.session_id == session_id)
                .order_by(FrameModel.time)
            )
            return list((await db.execute(ormstmt)).scalars().all())

    async def read_projection(
        self,
        session_id: SessionId,
        *,
        from_s: float | None = None,
        to_s: float | None = None,
        hz: Literal[10, 30, 60] = 30,
        fields: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        table = _table_for_hz(hz)
        # Field projection still happens in Python — see the row_dict
        # construction below. Pushing it into SQL with JSONB path operators
        # is a future optimization once we have benchmarks (plan §2.1).
        rows = await self._read_rows(session_id, hz=hz)

        # Filter time window (post-fetch — see comment above).
        start_time = rows[0].time if rows else None
        out: list[list[object]] = []
        for row in rows:
            t_rel = (row.time - start_time).total_seconds() if start_time else 0.0
            if from_s is not None and t_rel < from_s:
                continue
            if to_s is not None and t_rel > to_s:
                continue
            wheels = row.wheels or {}
            accel = (row.motion or {}).get("acceleration") or {}
            race = row.race or {}
            derived = row.derived or {}
            row_dict = {
                "speed": row.motion.get("speed_mps") if row.motion else None,
                "throttle": row.inputs.get("throttle") if row.inputs else None,
                "brake": row.inputs.get("brake") if row.inputs else None,
                "position": (
                    [
                        row.motion["position"]["x"],
                        row.motion["position"]["y"],
                        row.motion["position"]["z"],
                    ]
                    if row.motion and "position" in row.motion
                    else None
                ),
                "rpm": row.engine.get("rpm") if row.engine else None,
                "gear": row.drivetrain.get("gear") if row.drivetrain else None,
                "currentLapS": race.get("currentLapS"),
                "lastLapS": race.get("lastLapS"),
                "bestLapS": race.get("bestLapS"),
                "gripBudget": derived.get("gripBudgetUsed"),
                "acceleration": (
                    [accel.get("x"), accel.get("y"), accel.get("z")] if accel else None
                ),
                "tireTemp": (
                    [
                        (wheels.get("fl") or {}).get("tireTemp_normWindow"),
                        (wheels.get("fr") or {}).get("tireTemp_normWindow"),
                        (wheels.get("rl") or {}).get("tireTemp_normWindow"),
                        (wheels.get("rr") or {}).get("tireTemp_normWindow"),
                    ]
                    if wheels
                    else None
                ),
            }
            if fields is None:
                out.append(
                    [
                        t_rel,
                        row_dict["speed"],
                        row_dict["throttle"],
                        row_dict["brake"],
                        row_dict["position"],
                    ]
                )
            else:
                out.append([t_rel, *(row_dict.get(f) for f in fields)])

        return {
            "sessionId": session_id,
            "hz": hz,
            "fields": list(fields) if fields else ["speed", "throttle", "brake", "position"],
            "data": out,
            "_table": table,
        }

    async def last_frame_time(self, session_id: SessionId) -> datetime | None:
        async with self._sm() as db:
            stmt = (
                select(FrameModel.time)
                .where(FrameModel.session_id == session_id)
                .order_by(desc(FrameModel.time))
                .limit(1)
            )
            return (await db.execute(stmt)).scalar_one_or_none()

    async def bytes_used_by_car(self, car_id: CarId) -> int:
        # Approximate via pg_table_size restricted to car_id rows. MVP returns
        # a rough estimate (row count × estimated avg row width).
        async with self._sm() as db:
            stmt = text("SELECT COUNT(*) FROM frames WHERE car_id = :cid")
            row = (await db.execute(stmt, {"cid": car_id})).scalar_one()
            return int(row) * 1200  # ~1.2KB/row research R-3 estimate

    async def delete_session(self, session_id: SessionId) -> int:
        async with self._sm() as db:
            stmt = delete(FrameModel).where(FrameModel.session_id == session_id)
            result = await db.execute(stmt)
            await db.commit()
            return rowcount(result)

    async def read_last_position_snapshot(
        self, session_id: SessionId
    ) -> FramePositionSnapshot | None:
        async with self._sm() as db:
            stmt = (
                select(FrameModel.time, FrameModel.motion)
                .where(FrameModel.session_id == session_id)
                .order_by(desc(FrameModel.time))
                .limit(1)
            )
            row = (await db.execute(stmt)).first()
        if row is None:
            return None
        time_val, motion = row
        pos = (motion or {}).get("position") or {}
        orient = (motion or {}).get("orientation") or {}
        return FramePositionSnapshot(
            time=time_val,
            x=float(pos.get("x", 0.0)),
            y=float(pos.get("y", 0.0)),
            z=float(pos.get("z", 0.0)),
            yaw=float(orient.get("yaw", 0.0)),
        )

    async def read_position_track(self, session_id: SessionId) -> list[FramePositionSnapshot]:
        async with self._sm() as db:
            stmt = (
                select(FrameModel.time, FrameModel.motion)
                .where(FrameModel.session_id == session_id)
                .order_by(FrameModel.time)
            )
            rows = (await db.execute(stmt)).all()
        out: list[FramePositionSnapshot] = []
        for time_val, motion in rows:
            pos = (motion or {}).get("position") or {}
            orient = (motion or {}).get("orientation") or {}
            out.append(
                FramePositionSnapshot(
                    time=time_val,
                    x=float(pos.get("x", 0.0)),
                    y=float(pos.get("y", 0.0)),
                    z=float(pos.get("z", 0.0)),
                    yaw=float(orient.get("yaw", 0.0)),
                )
            )
        return out

    async def delete_frames_in_range(
        self,
        session_id: SessionId,
        *,
        after: datetime,
        before: datetime,
    ) -> int:
        async with self._sm() as db:
            stmt = delete(FrameModel).where(
                FrameModel.session_id == session_id,
                FrameModel.time > after,
                FrameModel.time < before,
            )
            result = await db.execute(stmt)
            await db.commit()
            return rowcount(result)
