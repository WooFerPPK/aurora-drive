"""T152: `/api/driver` router (API spec §5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query

from fh6.application.use_cases.rebuild_driver_fingerprint import RebuildDriverFingerprint
from fh6.domain.entities.driver_profile import DriverProfile
from fh6.infrastructure.ml.driver_fingerprint.baseline import TRAITS
from fh6.interfaces.dependencies import CarRepoDep, DriverRepoDep, SessionRepoDep
from fh6.interfaces.rest.schemas.driver import (
    DriverEvolutionResponse,
    DriverProfileResponse,
    DriverTrait,
)

router = APIRouter()


def profile_to_response(profile: DriverProfile) -> DriverProfileResponse:
    """Translate a `DriverProfile` to the wire response.

    The trait dicts are normalized to ensure every trait key is present
    with a default of 0.0 — frontends rely on the full 6-key shape.
    """
    fp = {k: profile.fingerprint.get(k, 0.0) for k in TRAITS}
    fp_baseline = {k: profile.fingerprint_baseline_90d.get(k, 0.0) for k in TRAITS}
    return DriverProfileResponse(
        lapsAnalyzed=profile.laps_analyzed,
        distanceAnalyzedM=profile.distance_analyzed_m,
        secondsAnalyzed=profile.seconds_analyzed,
        fingerprint=fp,
        fingerprintBaseline90d=fp_baseline,
        traits=[
            DriverTrait(
                id=str(t["id"]),
                name=str(t["name"]),
                score=float(t["score"]),
                blurb=str(t["blurb"]),
            )
            for t in profile.traits
        ],
        strengths=profile.strengths,
        weaknesses=profile.weaknesses,
        carAgnosticShare=profile.car_agnostic_share,
        persona=profile.persona,
        personaUpdatedAt=profile.persona_updated_at,
        modelVersion=profile.model_version,
    )


@router.get("/profile", response_model=DriverProfileResponse)
async def profile(
    driver_repo: DriverRepoDep,
    car_repo: CarRepoDep,
    session_repo: SessionRepoDep,
) -> DriverProfileResponse:
    rebuilder = RebuildDriverFingerprint(
        drivers=driver_repo,
        cars=car_repo,
        sessions=session_repo,
    )
    return profile_to_response(await rebuilder())


@router.get("/evolution", response_model=DriverEvolutionResponse)
async def evolution(
    driver_repo: DriverRepoDep,
    car_repo: CarRepoDep,
    session_repo: SessionRepoDep,
    days: int = Query(default=90, ge=1, le=365),
) -> DriverEvolutionResponse:
    rebuilder = RebuildDriverFingerprint(
        drivers=driver_repo,
        cars=car_repo,
        sessions=session_repo,
    )
    current = await rebuilder()
    now = datetime.now(UTC)

    points: list[tuple[float, dict[str, float]]] = []
    step = max(1, days // 12)
    for d in range(days, 0, -step):
        ts = (now - timedelta(days=d)).timestamp()
        points.append((ts, current.fingerprint))
    points.append((now.timestamp(), current.fingerprint))

    series: dict[str, list[list[float]]] = {trait: [] for trait in TRAITS}
    for ts, fp in points:
        for trait in TRAITS:
            series[trait].append([ts, fp.get(trait, 0.0)])

    return DriverEvolutionResponse(days=days, series=series, sessionClusters=[])
