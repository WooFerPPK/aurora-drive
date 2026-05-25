"""T139 / T141: `/api/predict` router (API spec §6, Clarification Q5)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from fh6.domain.entities.replay import WHAT_IF_TWEAK_KINDS
from fh6.domain.entities.session import Session
from fh6.domain.value_objects.ids import SessionId
from fh6.infrastructure.ml.best_achievable_lap.baseline import BestAchievableLapModel
from fh6.infrastructure.ml.crash_risk.baseline import CrashRiskModel
from fh6.infrastructure.ml.finish.baseline import FinishPositionModel
from fh6.infrastructure.ml.lap_residual.baseline import LapResidualModel
from fh6.infrastructure.ml.tire_wear.baseline_slip_energy import MODEL_VERSION
from fh6.infrastructure.ml.what_if_simulator import (
    UnsupportedWhatIfKind,
    WhatIfSimulator,
)
from fh6.interfaces.dependencies import (
    HotCacheDep,
    ReplayRepoDep,
    SessionRepoDep,
)
from fh6.interfaces.rest.errors import not_found, validation_error_400
from fh6.interfaces.rest.schemas.predict import (
    BestAchievableLapResponse,
    CrashRiskPredictionResponse,
    FinishPredictionResponse,
    LapPrediction,
    LapPredictionResponse,
    TireFailurePerCorner,
    TireFailurePredictionResponse,
    WhatIfPerTweak,
    WhatIfRequest,
    WhatIfResponse,
)

# Lap-prediction tuning. Tune these by name, not by re-reading the loop.
DEFAULT_PROJECTION_COUNT = 3
MAX_PROJECTION_COUNT = 10
CONFIDENCE_DECAY_PER_LAP = 0.9
SEED_WINDOW_LEN = 5

router = APIRouter()


async def _require_session(session_repo: SessionRepoDep, session_id: str) -> Session:
    s = await session_repo.get(SessionId(session_id))
    if s is None:
        raise not_found(f"session {session_id!r} not found", resource="session")
    return s


@router.get("/lap", response_model=LapPredictionResponse)
async def lap(
    session_repo: SessionRepoDep,
    hot_cache: HotCacheDep,
    sessionId: str = Query(...),
    n: int = Query(DEFAULT_PROJECTION_COUNT, ge=1, le=MAX_PROJECTION_COUNT),
) -> LapPredictionResponse:
    """Project the next ``n`` lap times (api-contract §6).

    - Seeds the LapResidualModel from ``Session.best_lap_s`` (replicated up
      to ``SEED_WINDOW_LEN`` times by ``lap_count``) and rolls the window
      forward across each projection so later laps condition on earlier ones.
    - Confidence is monotone non-increasing across ``k``: the raw model
      confidence is capped at the first projection's value (the model's raw
      confidence can rise as the seed window fills, so without a cap the
      net confidence is not strictly monotone), then multiplied by
      ``CONFIDENCE_DECAY_PER_LAP ** k``.
    - ``predictedAt`` reads ``raceTimeS`` from the most recent hot-cache
      frame for this (session, car). When no frame has arrived yet we fall
      back to ``0.0`` — callers should treat 0.0 as "no live frame yet".
    - ``limiter`` is ``None`` for now; tire-wear gating is a follow-up
      (backend work item 1).
    """
    s = await _require_session(session_repo, sessionId)

    latest = hot_cache.latest_for(s.id, s.car_id)
    predicted_at = (
        float(latest.raw.race.get("raceTimeS", 0.0) or 0.0) if latest is not None else 0.0
    )

    # Cold session: no best lap → nothing to project.
    if s.best_lap_s is None:
        return LapPredictionResponse(
            predictions=[],
            predictedAt=predicted_at,
            limiter=None,
            modelVersion=LapResidualModel().model_version,
            inputs=["best_lap_s", "lap_count", "raceTimeS"],
        )

    model = LapResidualModel()
    seed_len = max(1, min(s.lap_count or 0, SEED_WINDOW_LEN))
    seed: list[float] = [float(s.best_lap_s)] * seed_len
    base_lap = (s.lap_count or 0) + 1

    predictions: list[LapPrediction] = []
    last_conf = None
    first_conf_value: float | None = None
    for k in range(n):
        value, conf = model.predict(seed)
        conf_value = conf.value
        if first_conf_value is None:
            first_conf_value = conf_value
        else:
            conf_value = min(conf_value, first_conf_value)
        decay = CONFIDENCE_DECAY_PER_LAP**k
        band = conf.tolerance_band
        predictions.append(
            LapPrediction(
                lap=base_lap + k,
                time_s=value,
                lower_s=max(0.0, value - band),
                upper_s=value + band,
                confidence=max(0.0, min(1.0, conf_value * decay)),
            )
        )
        last_conf = conf
        seed = [*seed, value][-SEED_WINDOW_LEN:]

    model_version = last_conf.model_version if last_conf is not None else model.model_version
    return LapPredictionResponse(
        predictions=predictions,
        predictedAt=predicted_at,
        limiter=None,
        modelVersion=model_version,
        inputs=["best_lap_s", "lap_count", "raceTimeS"],
    )


@router.get("/tireFailure", response_model=TireFailurePredictionResponse)
async def tire_failure(
    session_repo: SessionRepoDep,
    hot_cache: HotCacheDep,
    sessionId: str = Query(...),
) -> TireFailurePredictionResponse:
    s = await _require_session(session_repo, sessionId)

    latest = hot_cache.latest_for(s.id, s.car_id) if hot_cache else None
    wear_map: dict[str, float] = {"fl": 0.0, "fr": 0.0, "rl": 0.0, "rr": 0.0}
    conf_value = 0.0
    model_version = MODEL_VERSION

    if latest is not None and latest.modeled is not None:
        for corner in ("fl", "fr", "rl", "rr"):
            wear_map[corner] = float(latest.modeled.tire_wear.get(corner, 0.0))
        conf_value = float(latest.modeled.tire_wear_confidence.value)
        model_version = latest.modeled.tire_wear_confidence.model_version

    laps_done = s.lap_count or 0
    per_corner: dict[str, TireFailurePerCorner] = {}
    for corner in ("fl", "fr", "rl", "rr"):
        wear = max(0.0, min(1.0, wear_map[corner]))
        failure_lap: int | None = None
        if laps_done > 0 and wear > 0.0:
            wear_per_lap = wear / laps_done
            if wear_per_lap > 0:
                remaining = (1.0 - wear) / wear_per_lap
                failure_lap = int(laps_done + max(0.0, remaining))
        per_corner[corner] = TireFailurePerCorner(
            wear=wear,
            failureAtLap=failure_lap,
            confidence=conf_value,
        )

    limiting: str | None = None
    best_lap = None
    for corner, pc in per_corner.items():
        if pc.failureAtLap is None:
            continue
        if best_lap is None or pc.failureAtLap < best_lap:
            best_lap = pc.failureAtLap
            limiting = corner
    if limiting is None:
        worst_wear = -1.0
        for corner, pc in per_corner.items():
            if pc.wear > worst_wear:
                worst_wear = pc.wear
                limiting = corner
        if worst_wear <= 0.0:
            limiting = None

    return TireFailurePredictionResponse(
        perCorner=per_corner,
        limitingCorner=limiting,
        modelVersion=model_version,
        inputs=["modeled.tireWear", "session.lap_count"],
    )


@router.get("/finish", response_model=FinishPredictionResponse)
async def finish(
    session_repo: SessionRepoDep,
    sessionId: str = Query(...),
) -> FinishPredictionResponse:
    await _require_session(session_repo, sessionId)
    model = FinishPositionModel()
    value, conf = model.predict(current_position=3, gap_to_leader_s=4.0, laps_remaining=3)
    return FinishPredictionResponse(
        value=float(value),
        confidence=conf.value,
        toleranceBand=conf.tolerance_band,
        modelVersion=conf.model_version,
        inputs=["current_position", "gap_to_leader_s", "laps_remaining"],
    )


@router.get("/crashRisk", response_model=CrashRiskPredictionResponse)
async def crash_risk(
    session_repo: SessionRepoDep,
    sessionId: str = Query(...),
) -> CrashRiskPredictionResponse:
    await _require_session(session_repo, sessionId)
    model = CrashRiskModel()
    value, conf = model.predict(
        avg_combined_slip=0.1,
        smashable_velocity_diff=0.0,
        speed_mps=40.0,
    )
    return CrashRiskPredictionResponse(
        value=value,
        confidence=conf.value,
        toleranceBand=conf.tolerance_band,
        modelVersion=conf.model_version,
        inputs=["avg_combined_slip", "smashable_velocity_diff", "speed_mps"],
    )


@router.get("/bestAchievableLap", response_model=BestAchievableLapResponse)
async def best_achievable_lap(
    session_repo: SessionRepoDep,
    sessionId: str = Query(...),
) -> BestAchievableLapResponse:
    s = await _require_session(session_repo, sessionId)
    model = BestAchievableLapModel()
    sectors = [s.best_lap_s / 3] * 3 if s.best_lap_s else []
    value, conf = model.predict(sectors)
    return BestAchievableLapResponse(
        value=value,
        confidence=conf.value,
        toleranceBand=conf.tolerance_band,
        modelVersion=conf.model_version,
        inputs=["sector_best_times"],
    )


@router.post("/whatIf", response_model=WhatIfResponse)
async def what_if(
    payload: WhatIfRequest,
    session_repo: SessionRepoDep,
    replay_repo: ReplayRepoDep,
) -> WhatIfResponse:
    await _require_session(session_repo, payload.sessionId)
    sim = WhatIfSimulator(replay_repo)
    try:
        result = await sim.run(
            session_id=SessionId(payload.sessionId),
            from_s=payload.fromS,
            to_s=payload.toS,
            tweaks=[t.model_dump() for t in payload.tweaks],
        )
    except UnsupportedWhatIfKind as exc:
        raise validation_error_400(
            str(exc),
            field="tweaks.kind",
            supported=sorted(WHAT_IF_TWEAK_KINDS),
        ) from exc
    return WhatIfResponse(
        sessionId=payload.sessionId,
        lapDeltaS=result.lap_delta_s,
        confidence=result.confidence.value,
        toleranceBand=result.confidence.tolerance_band,
        modelVersion=result.confidence.model_version,
        perTweak=[WhatIfPerTweak(kind=t.kind, deltaS=t.delta_s) for t in result.per_tweak],
        replayId=result.replay_id,
    )
