"""Postgres adapter for `ShiftPredictorRepository`.

Uses PostgreSQL INSERT ... ON CONFLICT DO UPDATE for all upserts so
concurrent writers and restart-resume scenarios land idempotently.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fh6.domain.ports.shift_predictor_repo import (
    BinRecord,
    ClassPriorBin,
    RatioRecord,
    ResetCounts,
    ShiftEventRow,
    TransmissionModeRecord,
)
from fh6.domain.value_objects.engine_fingerprint import EngineClassKey, EngineFingerprint
from fh6.domain.value_objects.ids import SessionId
from fh6.infrastructure.db.base import rowcount
from fh6.infrastructure.db.models.shift import (
    ClassPriorModel,
    EngineCurveModel,
    GearRatioModel,
    ShiftEventCleanModel,
    TransmissionModeModel,
)


class SqlShiftPredictorRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    # ------------------------------------------------------------------
    # Engine curve bins
    # ------------------------------------------------------------------

    async def upsert_bin(self, rec: BinRecord) -> None:
        fp = rec.fingerprint
        stmt = (
            insert(EngineCurveModel)
            .values(
                car_ordinal=fp.car_ordinal,
                performance_index=fp.performance_index,
                num_cylinders=fp.num_cylinders,
                gear=rec.gear,
                rpm_bin=rec.rpm_bin,
                count=rec.count,
                mean_torque_nm=rec.mean_torque_nm,
                m2_torque=rec.m2_torque,
                q90_torque_nm=rec.q90_torque_nm,
                mean_boost_psi=rec.mean_boost_psi,
                last_updated=rec.last_updated,
            )
            .on_conflict_do_update(
                index_elements=[
                    "car_ordinal",
                    "performance_index",
                    "num_cylinders",
                    "gear",
                    "rpm_bin",
                ],
                set_=dict(
                    count=rec.count,
                    mean_torque_nm=rec.mean_torque_nm,
                    m2_torque=rec.m2_torque,
                    q90_torque_nm=rec.q90_torque_nm,
                    mean_boost_psi=rec.mean_boost_psi,
                    last_updated=rec.last_updated,
                ),
            )
        )
        async with self._sm() as db:
            await db.execute(stmt)
            await db.commit()

    async def upsert_bins(self, recs: Sequence[BinRecord]) -> None:
        if not recs:
            return
        values = [
            dict(
                car_ordinal=r.fingerprint.car_ordinal,
                performance_index=r.fingerprint.performance_index,
                num_cylinders=r.fingerprint.num_cylinders,
                gear=r.gear,
                rpm_bin=r.rpm_bin,
                count=r.count,
                mean_torque_nm=r.mean_torque_nm,
                m2_torque=r.m2_torque,
                q90_torque_nm=r.q90_torque_nm,
                mean_boost_psi=r.mean_boost_psi,
                last_updated=r.last_updated,
            )
            for r in recs
        ]
        stmt = (
            insert(EngineCurveModel)
            .values(values)
            .on_conflict_do_update(
                index_elements=[
                    "car_ordinal",
                    "performance_index",
                    "num_cylinders",
                    "gear",
                    "rpm_bin",
                ],
                set_=dict(
                    count=insert(EngineCurveModel).excluded.count,
                    mean_torque_nm=insert(EngineCurveModel).excluded.mean_torque_nm,
                    m2_torque=insert(EngineCurveModel).excluded.m2_torque,
                    q90_torque_nm=insert(EngineCurveModel).excluded.q90_torque_nm,
                    mean_boost_psi=insert(EngineCurveModel).excluded.mean_boost_psi,
                    last_updated=insert(EngineCurveModel).excluded.last_updated,
                ),
            )
        )
        async with self._sm() as db:
            await db.execute(stmt)
            await db.commit()

    async def read_bins(self, fp: EngineFingerprint) -> list[BinRecord]:
        stmt = select(EngineCurveModel).where(
            EngineCurveModel.car_ordinal == fp.car_ordinal,
            EngineCurveModel.performance_index == fp.performance_index,
            EngineCurveModel.num_cylinders == fp.num_cylinders,
        )
        async with self._sm() as db:
            rows = (await db.execute(stmt)).scalars().all()
        return [
            BinRecord(
                fingerprint=EngineFingerprint(
                    car_ordinal=r.car_ordinal,
                    performance_index=r.performance_index,
                    num_cylinders=r.num_cylinders,
                ),
                gear=r.gear,
                rpm_bin=r.rpm_bin,
                count=r.count,
                mean_torque_nm=r.mean_torque_nm,
                m2_torque=r.m2_torque,
                q90_torque_nm=r.q90_torque_nm,
                mean_boost_psi=r.mean_boost_psi,
                last_updated=r.last_updated,
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Gear ratios
    # ------------------------------------------------------------------

    async def upsert_ratio(self, rec: RatioRecord) -> None:
        fp = rec.fingerprint
        stmt = (
            insert(GearRatioModel)
            .values(
                car_ordinal=fp.car_ordinal,
                performance_index=fp.performance_index,
                num_cylinders=fp.num_cylinders,
                gear=rec.gear,
                ratio=rec.ratio,
                variance=rec.variance,
                last_updated=rec.last_updated,
            )
            .on_conflict_do_update(
                index_elements=[
                    "car_ordinal",
                    "performance_index",
                    "num_cylinders",
                    "gear",
                ],
                set_=dict(
                    ratio=rec.ratio,
                    variance=rec.variance,
                    last_updated=rec.last_updated,
                ),
            )
        )
        async with self._sm() as db:
            await db.execute(stmt)
            await db.commit()

    async def read_ratios(self, fp: EngineFingerprint) -> list[RatioRecord]:
        stmt = select(GearRatioModel).where(
            GearRatioModel.car_ordinal == fp.car_ordinal,
            GearRatioModel.performance_index == fp.performance_index,
            GearRatioModel.num_cylinders == fp.num_cylinders,
        )
        async with self._sm() as db:
            rows = (await db.execute(stmt)).scalars().all()
        return [
            RatioRecord(
                fingerprint=EngineFingerprint(
                    car_ordinal=r.car_ordinal,
                    performance_index=r.performance_index,
                    num_cylinders=r.num_cylinders,
                ),
                gear=r.gear,
                ratio=r.ratio,
                variance=r.variance,
                last_updated=r.last_updated,
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Class priors
    # ------------------------------------------------------------------

    async def upsert_class_prior_bin(self, rec: ClassPriorBin) -> None:
        key = rec.class_key
        stmt = (
            insert(ClassPriorModel)
            .values(
                car_class=key.car_class,
                car_group=key.car_group,
                drivetrain_type=key.drivetrain_type,
                num_cylinders=key.num_cylinders,
                gear=rec.gear,
                rpm_bin=rec.rpm_bin,
                count=rec.count,
                q90_torque_nm=rec.q90_torque_nm,
                last_built=rec.last_built,
            )
            .on_conflict_do_update(
                index_elements=[
                    "car_class",
                    "car_group",
                    "drivetrain_type",
                    "num_cylinders",
                    "gear",
                    "rpm_bin",
                ],
                set_=dict(
                    count=rec.count,
                    q90_torque_nm=rec.q90_torque_nm,
                    last_built=rec.last_built,
                ),
            )
        )
        async with self._sm() as db:
            await db.execute(stmt)
            await db.commit()

    async def read_class_prior(self, key: EngineClassKey) -> list[ClassPriorBin]:
        stmt = select(ClassPriorModel).where(
            ClassPriorModel.car_class == key.car_class,
            ClassPriorModel.car_group == key.car_group,
            ClassPriorModel.drivetrain_type == key.drivetrain_type,
            ClassPriorModel.num_cylinders == key.num_cylinders,
        )
        async with self._sm() as db:
            rows = (await db.execute(stmt)).scalars().all()
        return [
            ClassPriorBin(
                class_key=EngineClassKey(
                    car_class=r.car_class,
                    car_group=r.car_group,
                    drivetrain_type=r.drivetrain_type,
                    num_cylinders=r.num_cylinders,
                ),
                gear=r.gear,
                rpm_bin=r.rpm_bin,
                count=r.count,
                q90_torque_nm=r.q90_torque_nm,
                last_built=r.last_built,
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Shift events
    # ------------------------------------------------------------------

    async def record_shift_event(self, row: ShiftEventRow) -> None:
        fp = row.fingerprint
        async with self._sm() as db:
            db.add(
                ShiftEventCleanModel(
                    session_id=str(row.session_id),
                    car_ordinal=fp.car_ordinal,
                    performance_index=fp.performance_index,
                    num_cylinders=fp.num_cylinders,
                    shift_at=row.shift_at,
                    gear_from=row.gear_from,
                    gear_to=row.gear_to,
                    actual_rpm=row.actual_rpm,
                    recommended_rpm=row.recommended_rpm,
                    recommendation_conf=row.recommendation_conf,
                    predicted_post_torque=row.predicted_post_torque,
                    measured_post_torque=row.measured_post_torque,
                    est_cost_s=row.est_cost_s,
                    post_shift_rpm=row.post_shift_rpm,
                    recommended_post_rpm=row.recommended_post_rpm,
                )
            )
            await db.commit()

    async def read_shift_events(self, session_id: SessionId) -> list[ShiftEventRow]:
        stmt = (
            select(ShiftEventCleanModel)
            .where(ShiftEventCleanModel.session_id == str(session_id))
            .order_by(ShiftEventCleanModel.shift_at)
        )
        async with self._sm() as db:
            rows = (await db.execute(stmt)).scalars().all()
        return [
            ShiftEventRow(
                id=r.id,
                session_id=SessionId(r.session_id),
                fingerprint=EngineFingerprint(
                    car_ordinal=r.car_ordinal,
                    performance_index=r.performance_index,
                    num_cylinders=r.num_cylinders,
                ),
                shift_at=r.shift_at,
                gear_from=r.gear_from,
                gear_to=r.gear_to,
                actual_rpm=r.actual_rpm,
                recommended_rpm=r.recommended_rpm,
                recommendation_conf=r.recommendation_conf,
                predicted_post_torque=r.predicted_post_torque,
                measured_post_torque=r.measured_post_torque,
                est_cost_s=r.est_cost_s,
                post_shift_rpm=r.post_shift_rpm,
                recommended_post_rpm=r.recommended_post_rpm,
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Class-key fingerprint aggregation
    # ------------------------------------------------------------------

    async def list_fingerprints_for_class_key(
        self,
        *,
        candidate_fingerprints: Sequence[EngineFingerprint],
        min_total_samples: int,
    ) -> list[tuple[EngineFingerprint, int]]:
        # Empty candidate set short-circuits — `tuple_(...).in_(())` is invalid SQL.
        if not candidate_fingerprints:
            return []

        candidates = [
            (fp.car_ordinal, fp.performance_index, fp.num_cylinders)
            for fp in candidate_fingerprints
        ]
        total_col = func.sum(EngineCurveModel.count).label("total")
        stmt = (
            select(
                EngineCurveModel.car_ordinal,
                EngineCurveModel.performance_index,
                EngineCurveModel.num_cylinders,
                total_col,
            )
            .where(
                tuple_(
                    EngineCurveModel.car_ordinal,
                    EngineCurveModel.performance_index,
                    EngineCurveModel.num_cylinders,
                ).in_(candidates)
            )
            .group_by(
                EngineCurveModel.car_ordinal,
                EngineCurveModel.performance_index,
                EngineCurveModel.num_cylinders,
            )
            .having(func.sum(EngineCurveModel.count) >= min_total_samples)
        )
        async with self._sm() as db:
            result = await db.execute(stmt)
            rows = result.all()
        return [
            (
                EngineFingerprint(
                    car_ordinal=r.car_ordinal,
                    performance_index=r.performance_index,
                    num_cylinders=r.num_cylinders,
                ),
                int(r.total),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Transmission mode
    # ------------------------------------------------------------------

    async def upsert_transmission_mode(self, rec: TransmissionModeRecord) -> None:
        fp = rec.fingerprint
        stmt = (
            insert(TransmissionModeModel)
            .values(
                car_ordinal=fp.car_ordinal,
                performance_index=fp.performance_index,
                num_cylinders=fp.num_cylinders,
                mode=rec.mode,
                confidence=rec.confidence,
                sample_count=rec.sample_count,
                last_updated=rec.last_updated,
            )
            .on_conflict_do_update(
                index_elements=[
                    "car_ordinal",
                    "performance_index",
                    "num_cylinders",
                ],
                set_=dict(
                    mode=rec.mode,
                    confidence=rec.confidence,
                    sample_count=rec.sample_count,
                    last_updated=rec.last_updated,
                ),
            )
        )
        async with self._sm() as db:
            await db.execute(stmt)
            await db.commit()

    async def read_transmission_mode(self, fp: EngineFingerprint) -> TransmissionModeRecord | None:
        stmt = select(TransmissionModeModel).where(
            TransmissionModeModel.car_ordinal == fp.car_ordinal,
            TransmissionModeModel.performance_index == fp.performance_index,
            TransmissionModeModel.num_cylinders == fp.num_cylinders,
        )
        async with self._sm() as db:
            row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return TransmissionModeRecord(
            fingerprint=EngineFingerprint(
                car_ordinal=row.car_ordinal,
                performance_index=row.performance_index,
                num_cylinders=row.num_cylinders,
            ),
            mode=row.mode,
            confidence=row.confidence,
            sample_count=row.sample_count,
            last_updated=row.last_updated,
        )

    async def delete_transmission_mode(self, fp: EngineFingerprint) -> int:
        stmt = delete(TransmissionModeModel).where(
            TransmissionModeModel.car_ordinal == fp.car_ordinal,
            TransmissionModeModel.performance_index == fp.performance_index,
            TransmissionModeModel.num_cylinders == fp.num_cylinders,
        )
        async with self._sm() as db:
            result = await db.execute(stmt)
            await db.commit()
        return rowcount(result)

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    async def reset_fingerprint(self, fp: EngineFingerprint) -> ResetCounts:
        dict(
            car_ordinal=fp.car_ordinal,
            performance_index=fp.performance_index,
            num_cylinders=fp.num_cylinders,
        )
        async with self._sm() as db:
            curve_result = await db.execute(
                delete(EngineCurveModel).where(
                    EngineCurveModel.car_ordinal == fp.car_ordinal,
                    EngineCurveModel.performance_index == fp.performance_index,
                    EngineCurveModel.num_cylinders == fp.num_cylinders,
                )
            )
            ratio_result = await db.execute(
                delete(GearRatioModel).where(
                    GearRatioModel.car_ordinal == fp.car_ordinal,
                    GearRatioModel.performance_index == fp.performance_index,
                    GearRatioModel.num_cylinders == fp.num_cylinders,
                )
            )
            event_result = await db.execute(
                delete(ShiftEventCleanModel).where(
                    ShiftEventCleanModel.car_ordinal == fp.car_ordinal,
                    ShiftEventCleanModel.performance_index == fp.performance_index,
                    ShiftEventCleanModel.num_cylinders == fp.num_cylinders,
                )
            )
            await db.commit()
        return ResetCounts(
            engine_curves=rowcount(curve_result),
            gear_ratios=rowcount(ratio_result),
            shift_events=rowcount(event_result),
        )
