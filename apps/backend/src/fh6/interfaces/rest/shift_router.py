"""`/api/predict/shift*` router (FR-021, FR-022, FR-023).

Wired into the FastAPI app at `/api/predict/shift` so endpoints become
`GET /api/predict/shift`, `GET /api/predict/shift/report`, and
`POST /api/predict/shift/reset`. Deps come from `interfaces.dependencies`
factories; the router never instantiates the predictor.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query

from fh6.application.services.hot_cache import HotCache
from fh6.domain.entities.session import Session
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint
from fh6.domain.value_objects.ids import SessionId
from fh6.interfaces.dependencies import (
    HotCacheDep,
    SessionRepoDep,
    ShiftPredictorDep,
    ShiftRepoDep,
)
from fh6.interfaces.rest.errors import not_found, validation_error_400
from fh6.interfaces.rest.schemas.shift import (
    Fingerprint,
    ShiftPredictResponse,
    ShiftReportPairAgg,
    ShiftReportResponse,
    ShiftResetCounts,
    ShiftResetRequest,
    ShiftResetResponse,
)

router = APIRouter()


_PREDICT_INPUTS = [
    "engine.torque_nm",
    "engine.rpm",
    "engine.boost_psi",
    "motion.speed_mps",
    "drivetrain.gear",
    "inputs.throttle",
    "wheels.*.combinedSlip",
    "world.carOrdinal",
    "world.performanceIndex",
]


async def _resolve_session(
    session_repo: SessionRepoDep,
    session_id: str,
) -> Session:
    """Resolve `sessionId` query/body value. `"live"` → latest in-flight."""
    if session_id == "live":
        s = await session_repo.latest_in_flight()
        if s is None:
            raise not_found("no in-flight session", resource="session")
        return s
    s = await session_repo.get(SessionId(session_id))
    if s is None:
        raise not_found(f"session {session_id!r} not found", resource="session")
    return s


def _fingerprint_for_session(hot_cache: HotCache, session: Session) -> EngineFingerprint:
    """Look up the latest hot-cache frame for the session and read its fingerprint."""
    latest = hot_cache.latest_for(session.id, session.car_id) if hot_cache else None
    if latest is None:
        raise not_found(
            "no live frame for session yet; fingerprint unknown",
            resource="frame",
        )
    return EngineFingerprint.from_frame_raw(latest.raw)


def _isoformat(at: datetime | None) -> str | None:
    if at is None:
        return None
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    return at.isoformat().replace("+00:00", "Z")


@router.get("", response_model=ShiftPredictResponse)
async def get_shift_prediction(
    session_repo: SessionRepoDep,
    hot_cache: HotCacheDep,
    shift_predictor: ShiftPredictorDep,
    sessionId: str = Query(...),
) -> ShiftPredictResponse:
    """FR-021: current shift recommendation for the session's fingerprint."""
    s = await _resolve_session(session_repo, sessionId)
    fp = _fingerprint_for_session(hot_cache, s)

    snap = shift_predictor.get_snapshot(fp)

    return ShiftPredictResponse(
        fingerprint=Fingerprint(
            carOrdinal=fp.car_ordinal,
            performanceIndex=fp.performance_index,
            numCylinders=fp.num_cylinders,
        ),
        byGear={str(k): v for k, v in snap.by_gear.items()},
        confidenceByGear={str(k): v for k, v in snap.confidence_by_gear.items()},
        ratios={str(k): v for k, v in snap.ratios.items()},
        ratioConfidenceByGear={str(k): v for k, v in snap.ratio_confidence_by_gear.items()},
        stage=snap.stage,
        trainedSampleCount=snap.trained_sample_count,
        lastUpdated=_isoformat(snap.last_updated),
        confidence=snap.overall_confidence,
        inputs=list(_PREDICT_INPUTS),
        modelVersion=snap.model_version,
    )


@router.get("/report", response_model=ShiftReportResponse)
async def get_shift_report(
    session_repo: SessionRepoDep,
    shift_repo: ShiftRepoDep,
    shift_predictor: ShiftPredictorDep,
    sessionId: str = Query(...),
) -> ShiftReportResponse:
    """FR-022 / FR-051: per-session shift report aggregated from shift_events_clean."""
    s = await _resolve_session(session_repo, sessionId)
    rows = await shift_repo.read_shift_events(s.id)

    by_pair: dict[tuple[int, int], dict[str, Any]] = {}
    delta_rpms: list[float] = []
    est_total = 0.0
    clean_shifts = 0

    for ev in rows:
        clean_shifts += 1
        direction = "up" if ev.gear_to > ev.gear_from else "down"
        key = (ev.gear_from, ev.gear_to)
        bucket = by_pair.setdefault(
            key,
            {
                "n": 0,
                "delta_sum": 0.0,
                "cost_sum": 0.0,
                "direction": direction,
            },
        )
        bucket["n"] += 1

        cost = float(ev.est_cost_s) if ev.est_cost_s is not None else 0.0
        bucket["cost_sum"] += cost
        est_total += cost

        if direction == "up":
            if ev.recommended_rpm is not None:
                delta = float(ev.actual_rpm) - float(ev.recommended_rpm)
                bucket["delta_sum"] += delta
                delta_rpms.append(delta)
        elif ev.post_shift_rpm is not None and ev.recommended_post_rpm is not None:
            delta = float(ev.post_shift_rpm) - float(ev.recommended_post_rpm)
            bucket["delta_sum"] += delta
            delta_rpms.append(delta)

    pair_aggs: dict[str, ShiftReportPairAgg] = {}
    for (g_from, g_to), b in by_pair.items():
        n = b["n"]
        avg_delta = b["delta_sum"] / n if n else 0.0
        avg_cost = b["cost_sum"] / n if n else 0.0
        pair_aggs[f"{g_from}->{g_to}"] = ShiftReportPairAgg(
            n=n,
            avgDeltaRpm=avg_delta,
            avgEstCostS=avg_cost,
            direction=b["direction"],
        )

    assist_intervention_pct: float = 0.0
    if shift_predictor is not None and hasattr(shift_predictor, "get_session_assist_pct"):
        assist_intervention_pct = shift_predictor.get_session_assist_pct(s.id)

    return ShiftReportResponse(
        sessionId=str(s.id),
        totalShifts=clean_shifts,
        cleanShifts=clean_shifts,
        avgDeltaRpm=sum(delta_rpms) / len(delta_rpms) if delta_rpms else 0.0,
        byGearPair=pair_aggs,
        estTotalCostS=est_total,
        modelVersion="shift-v1",
        assistInterventionPct=assist_intervention_pct,
    )


@router.post("/reset", response_model=ShiftResetResponse)
async def post_shift_reset(
    payload: ShiftResetRequest,
    session_repo: SessionRepoDep,
    hot_cache: HotCacheDep,
    shift_predictor: ShiftPredictorDep,
) -> ShiftResetResponse:
    """FR-023: drop in-memory + on-disk state for a fingerprint."""
    if payload.sessionId is not None:
        s = await _resolve_session(session_repo, payload.sessionId)
        fp = _fingerprint_for_session(hot_cache, s)
    elif (
        payload.carOrdinal is not None
        and payload.performanceIndex is not None
        and payload.numCylinders is not None
    ):
        fp = EngineFingerprint(
            car_ordinal=payload.carOrdinal,
            performance_index=payload.performanceIndex,
            num_cylinders=payload.numCylinders,
        )
    else:
        raise validation_error_400(
            "either sessionId or full fingerprint must be supplied",
            field="body",
        )

    counts = await shift_predictor.reset(fp)
    return ShiftResetResponse(
        deleted=ShiftResetCounts(
            engineCurves=int(counts.engine_curves),
            gearRatios=int(counts.gear_ratios),
            shiftEvents=int(counts.shift_events),
            transmissionModes=int(counts.transmission_modes),
        ),
    )
