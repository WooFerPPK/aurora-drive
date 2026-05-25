"""`/api/track` router (API spec §8). T041 (current) + T077 (optimal-line) + T078 (mistakes)."""

from __future__ import annotations

from fastapi import APIRouter, Query

from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.infrastructure.ml.track_inference.cluster import open_world_default
from fh6.interfaces.dependencies import FrameStoreDep, SessionRepoDep
from fh6.interfaces.rest.errors import not_found
from fh6.interfaces.rest.schemas.track import (
    MistakeBreakdown,
    MistakeBucket,
    MistakesHeatmapResponse,
    MistakeTrendPoint,
    OptimalLinePoint,
    OptimalLineResponse,
    SectorDelta,
    TrackCurrentResponse,
)

router = APIRouter()


@router.get("/current", response_model=TrackCurrentResponse)
async def track_current() -> TrackCurrentResponse:
    """API spec §8 `GET /api/track/current`. Always returns
    `inferred=true` in MVP (FR-019)."""
    track = open_world_default()
    return TrackCurrentResponse(
        trackId=track.id,
        displayName=track.display_name,
        inferred=track.inferred,
        outline=[list(p) for p in (track.outline or [])],
        corners=track.corners or [],
    )


@router.get("/optimal-line", response_model=OptimalLineResponse)
async def optimal_line(
    session_repo: SessionRepoDep,
    frame_store: FrameStoreDep,
    sessionId: str = Query(...),
) -> OptimalLineResponse:
    """T077: AI-computed optimal line vs. driver's line.

    MVP returns the recorded line on both sides (your-line == optimal-line)
    and an empty incidents list. Full optimal-line synthesis lands when
    the lap-residual + corner-detection models stabilise (US5/US6).
    """
    session = await session_repo.get(SessionId(sessionId))
    if session is None:
        raise not_found(f"session {sessionId!r} not found", resource="session")

    projection = await frame_store.read_projection(
        SessionId(sessionId),
        hz=10,
        fields=("position", "speed", "throttle", "brake"),
    )
    data = projection.get("data") or []
    points: list[OptimalLinePoint] = []
    for row in data:
        t, pos, speed, throttle, brake = row[0], row[1], row[2], row[3], row[4]
        x, y = (pos[0], pos[2]) if pos else (0.0, 0.0)
        points.append(
            OptimalLinePoint(
                t=float(t),
                x=float(x),
                y=float(y),
                speed=float(speed or 0.0),
                throttle=float(throttle or 0.0),
                brake=float(brake or 0.0),
            )
        )
    return OptimalLineResponse(
        sessionId=sessionId,
        trackId=str(session.track_id) if session.track_id else "open_world",
        optimalLine=points,
        yourLine=points,
        incidents=[],
        sectorDeltas=[SectorDelta(sector=0, deltaS=0.0)],
    )


@router.get("/mistakes", response_model=MistakesHeatmapResponse)
async def mistakes(
    session_repo: SessionRepoDep,
    carId: str = Query(...),
    trackId: str | None = Query(default=None),
) -> MistakesHeatmapResponse:
    """T078: aggregated mistake heatmap. MVP returns the documented
    shape with zero buckets until detectors persist mistakes (lands with
    coach detectors in US3 / event detectors in US1)."""
    cid = CarId(carId)
    sessions = await session_repo.list_for_car(cid, limit=1000)
    if trackId is not None:
        sessions = [s for s in sessions if s.track_id == trackId]

    buckets: list[MistakeBucket] = []
    breakdown: list[MistakeBreakdown] = []
    trend: list[MistakeTrendPoint] = []
    return MistakesHeatmapResponse(
        carId=carId,
        trackId=trackId,
        buckets=buckets,
        breakdown=breakdown,
        trend=trend,
    )
