"""Postgres-backed `PredictionRepository`.

Each prediction snapshot is one row. The current `/api/predict/*`
routers compute predictions on-demand and don't persist; this adapter
is preemptive infrastructure for the upcoming "show prediction history"
flows (Phase ?). Wired onto app.state so consumers can reach it via
`Depends()` once they arrive.

`Confidence` is decomposed into three columns
(`confidence_value`, `confidence_tolerance_band`, `model_version`) so
queries don't have to dig into a JSON payload to filter on confidence.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fh6.domain.entities.prediction import Prediction, PredictionKind
from fh6.domain.value_objects.confidence import Confidence
from fh6.domain.value_objects.ids import SessionId
from fh6.infrastructure.db.models.predictions import PredictionModel


class PgPredictionRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    @staticmethod
    def _to_row(p: Prediction) -> PredictionModel:
        return PredictionModel(
            id=p.id,
            kind=p.kind.value,
            session_id=str(p.session_id),
            predicted_at_session_seconds=p.predicted_at_session_seconds,
            payload=dict(p.payload),
            model_version=p.confidence.model_version,
            confidence_value=p.confidence.value,
            confidence_tolerance_band=p.confidence.tolerance_band,
            inputs=list(p.inputs),
        )

    @staticmethod
    def _to_domain(row: PredictionModel) -> Prediction:
        return Prediction(
            id=row.id,
            kind=PredictionKind(row.kind),
            session_id=SessionId(row.session_id),
            predicted_at_session_seconds=row.predicted_at_session_seconds,
            payload=dict(row.payload or {}),
            confidence=Confidence(
                value=row.confidence_value,
                tolerance_band=row.confidence_tolerance_band,
                model_version=row.model_version,
            ),
            inputs=list(row.inputs or []),
        )

    async def save(self, prediction: Prediction) -> None:
        async with self._sm() as db:
            db.add(self._to_row(prediction))
            await db.commit()

    async def list_for_session(
        self, session_id: SessionId, *, kind: PredictionKind | None = None
    ) -> list[Prediction]:
        async with self._sm() as db:
            stmt = select(PredictionModel).where(PredictionModel.session_id == str(session_id))
            if kind is not None:
                stmt = stmt.where(PredictionModel.kind == kind.value)
            stmt = stmt.order_by(PredictionModel.predicted_at_session_seconds, PredictionModel.id)
            rows = (await db.execute(stmt)).scalars().all()
            return [self._to_domain(r) for r in rows]
