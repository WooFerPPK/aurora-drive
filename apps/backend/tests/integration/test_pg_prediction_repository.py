"""Integration tests for `PgPredictionRepository`."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fh6.domain.entities.prediction import Prediction, PredictionKind
from fh6.domain.value_objects.confidence import Confidence
from fh6.domain.value_objects.ids import SessionId
from fh6.infrastructure.db.repositories.predictions import PgPredictionRepository


def _prediction(
    *,
    id: str,
    session_id: str,
    kind: PredictionKind = PredictionKind.LAP,
    at: float = 60.0,
    value: float = 0.8,
    band: float = 0.05,
    model_version: str = "lap_v1",
) -> Prediction:
    return Prediction(
        id=id,
        kind=kind,
        session_id=SessionId(session_id),
        predicted_at_session_seconds=at,
        payload={"laps_remaining": 4},
        confidence=Confidence(value=value, tolerance_band=band, model_version=model_version),
        inputs=["throttle_smoothness", "lap_consistency"],
    )


@pytest.mark.asyncio
async def test_list_empty_for_unknown_session(
    pg_db: async_sessionmaker[AsyncSession],
) -> None:
    repo = PgPredictionRepository(pg_db)
    assert await repo.list_for_session(SessionId("ses_none")) == []


@pytest.mark.asyncio
async def test_save_then_list_orders_by_predicted_at(
    pg_db: async_sessionmaker[AsyncSession], seeded_session_id: str
) -> None:
    repo = PgPredictionRepository(pg_db)
    await repo.save(_prediction(id="p2", session_id=seeded_session_id, at=20.0))
    await repo.save(_prediction(id="p1", session_id=seeded_session_id, at=10.0))
    await repo.save(_prediction(id="p3", session_id=seeded_session_id, at=30.0))

    got = await repo.list_for_session(SessionId(seeded_session_id))
    assert [p.id for p in got] == ["p1", "p2", "p3"]
    assert got[0].confidence == Confidence(value=0.8, tolerance_band=0.05, model_version="lap_v1")


@pytest.mark.asyncio
async def test_list_filters_by_kind(
    pg_db: async_sessionmaker[AsyncSession], seeded_session_id: str
) -> None:
    repo = PgPredictionRepository(pg_db)
    await repo.save(_prediction(id="p_lap", session_id=seeded_session_id, kind=PredictionKind.LAP))
    await repo.save(
        _prediction(id="p_tire", session_id=seeded_session_id, kind=PredictionKind.TIRE_FAILURE)
    )

    got = await repo.list_for_session(SessionId(seeded_session_id), kind=PredictionKind.LAP)
    assert [p.id for p in got] == ["p_lap"]
