"""T073 / T074 / T075: `/api/sessions` router (API spec §3)."""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, status
from fastapi.responses import Response

from fh6.application.use_cases.get_session_detail import GetSessionDetail
from fh6.application.use_cases.get_session_frames import (
    GetSessionFrames,
    UnsupportedField,
    UnsupportedHz,
)
from fh6.application.use_cases.rebuild_driver_fingerprint import (
    BuildSessionDriverProfile,
)
from fh6.domain.entities.session import Session
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.interfaces.dependencies import (
    CoachRepoDep,
    FrameStoreDep,
    LapRepoDep,
    SessionEventsRepoDep,
    SessionRepoDep,
)
from fh6.interfaces.rest.driver_router import profile_to_response
from fh6.interfaces.rest.errors import not_found, validation_error_400
from fh6.interfaces.rest.schemas.driver import DriverProfileResponse
from fh6.interfaces.rest.schemas.sessions import (
    LapRollup,
    SessionDetailResponse,
    SessionEventEntry,
    SessionFramesResponse,
    SessionListItem,
    SessionPatchRequest,
    TimelinePoint,
)

router = APIRouter()


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"o": offset}).encode()).decode()


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None or not cursor:
        return 0
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return int(payload.get("o", 0))
    except Exception as e:  # pragma: no cover
        raise validation_error_400("invalid cursor", field="cursor") from e


def _serialize_session(s: Session) -> SessionListItem:
    return SessionListItem(
        id=str(s.id),
        carId=str(s.car_id),
        type=s.type.value,
        startedAt=s.started_at,
        endedAt=s.ended_at,
        durationS=s.duration_s,
        lapCount=s.lap_count,
        bestLapS=s.best_lap_s,
        topSpeedMps=s.top_speed_mps,
        distanceM=s.distance_m,
        trackId=str(s.track_id) if s.track_id else None,
        summary=s.summary,
        closedReason=s.closed_reason.value if s.closed_reason else None,
        name=s.name,
        bookmarked=s.bookmarked,
    )


@router.get("/current", response_model=SessionListItem)
async def current_session(session_repo: SessionRepoDep) -> SessionListItem:
    """Return the most recent in-flight session (ended_at IS NULL).

    The live UI polls this to find the session id to wire predictions,
    coach feed, and session detail against. 404 when nothing is open.
    """
    s = await session_repo.latest_in_flight()
    if s is None:
        raise not_found("no in-flight session", resource="session")
    return _serialize_session(s)


@router.get("", response_model=list[SessionListItem])
async def list_sessions(
    response: Response,
    session_repo: SessionRepoDep,
    carId: str | None = Query(default=None),
    type: str | None = Query(default=None),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    cursor: str | None = Query(default=None),
) -> list[SessionListItem]:
    if carId is None:
        sessions: list[Session] = await session_repo.list_all(limit=10_000)
    else:
        sessions = await session_repo.list_for_car(CarId(carId), limit=10_000)
    # Ordering rule: bookmarked first, then started_at desc.
    sessions.sort(key=lambda s: (s.bookmarked, s.started_at), reverse=True)

    if type is not None:
        sessions = [s for s in sessions if s.type.value == type]
    if from_ is not None:
        sessions = [s for s in sessions if s.started_at >= from_]
    if to is not None:
        sessions = [s for s in sessions if s.started_at <= to]

    start = _decode_cursor(cursor)
    end = start + limit
    page = sessions[start:end]
    # Response shape is a bare list (frontend contract); cursor for the
    # next page lives in a header so pagination still works without an
    # envelope. Header is omitted when the current page is the last.
    if end < len(sessions):
        response.headers["X-Next-Cursor"] = _encode_cursor(end)
    return [_serialize_session(s) for s in page]


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def session_detail(
    session_id: str,
    session_repo: SessionRepoDep,
    frame_store: FrameStoreDep,
    coach_repo: CoachRepoDep,
    lap_repo: LapRepoDep,
    session_events_repo: SessionEventsRepoDep,
) -> SessionDetailResponse:
    use_case = GetSessionDetail(
        session_repo,
        frame_store,
        coach_repo,
        lap_repo,
        session_events_repo,
    )
    detail = await use_case(SessionId(session_id))
    if detail is None:
        raise not_found(f"session {session_id!r} not found", resource="session")
    s = detail.session
    return SessionDetailResponse(
        id=str(s.id),
        carId=str(s.car_id),
        type=s.type.value,
        startedAt=s.started_at,
        endedAt=s.ended_at,
        durationS=s.duration_s,
        lapCount=s.lap_count,
        bestLapS=s.best_lap_s,
        topSpeedMps=s.top_speed_mps,
        distanceM=s.distance_m,
        trackId=str(s.track_id) if s.track_id else None,
        summary=s.summary,
        closedReason=s.closed_reason.value if s.closed_reason else None,
        name=s.name,
        bookmarked=s.bookmarked,
        styleDriftDelta=s.style_drift_delta,
        lapRollups=[
            LapRollup(
                lap=r.lap,
                timeS=r.time_s,
                sectorTimes=r.sector_times,
                topSpeedMps=r.top_speed_mps,
                avgThrottle=r.avg_throttle,
                avgBrake=r.avg_brake,
            )
            for r in detail.lap_rollups
        ],
        perCornerStats=[],
        callouts=detail.callouts,
        timeline10hz=[
            TimelinePoint(t=p["t"], speed=p["speed"], throttle=p["throttle"], brake=p["brake"])
            for p in detail.timeline_10hz
        ],
        events=[
            SessionEventEntry(atS=e.at_s, kind=e.kind, payload=dict(e.payload))
            for e in detail.events
        ],
    )


@router.get("/{session_id}/frames", response_model=SessionFramesResponse)
async def session_frames(
    session_id: str,
    frame_store: FrameStoreDep,
    hz: int = Query(default=30),
    fields: str | None = Query(default=None),
    from_s: float | None = Query(default=None, alias="from"),
    to_s: float | None = Query(default=None, alias="to"),
) -> SessionFramesResponse:
    use_case = GetSessionFrames(frame_store)
    try:
        parsed_hz = use_case.parse_hz(hz)
        parsed_fields = use_case.parse_fields(fields)
    except UnsupportedHz as exc:
        raise validation_error_400(str(exc), field="hz", supported=["10", "30", "60"]) from exc
    except UnsupportedField as exc:
        raise validation_error_400(
            str(exc), field="fields", supported=sorted(["speed", "throttle", "brake", "position"])
        ) from exc

    payload = await use_case(
        SessionId(session_id),
        hz=parsed_hz,
        fields=parsed_fields,
        from_s=from_s,
        to_s=to_s,
    )
    data: list[list[Any]] = payload.get("data") or []  # type: ignore[assignment]
    return SessionFramesResponse(
        sessionId=session_id,
        hz=parsed_hz,
        fields=parsed_fields,
        data=data,
    )


@router.get("/{session_id}/driver-profile", response_model=DriverProfileResponse)
async def session_driver_profile(
    session_id: str,
    session_repo: SessionRepoDep,
) -> DriverProfileResponse:
    session = await session_repo.get(SessionId(session_id))
    if session is None:
        raise not_found(f"session {session_id!r} not found", resource="session")
    use_case = BuildSessionDriverProfile(sessions=session_repo)
    profile = await use_case(session)
    return profile_to_response(profile)


@router.patch("/{session_id}", response_model=SessionListItem)
async def patch_session(
    session_id: str,
    body: SessionPatchRequest,
    session_repo: SessionRepoDep,
) -> SessionListItem:
    sid = SessionId(session_id)
    provided = body.model_fields_set
    if not provided:
        # No-op patch: return current resource. 404 if missing so the client
        # can distinguish unknown id from successful no-op.
        s = await session_repo.get(sid)
        if s is None:
            raise not_found(f"session {session_id!r} not found", resource="session")
        return _serialize_session(s)
    updated: Session | None = None
    if "name" in provided:
        # Empty/whitespace clears to NULL — repo enforces the trim rule.
        updated = await session_repo.rename(sid, body.name)
        if updated is None:
            raise not_found(f"session {session_id!r} not found", resource="session")
    if "bookmarked" in provided:
        bookmarked = bool(body.bookmarked)
        updated = await session_repo.set_bookmark(sid, bookmarked)
        if updated is None:
            raise not_found(f"session {session_id!r} not found", resource="session")
    assert updated is not None
    return _serialize_session(updated)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_sessions(
    session_repo: SessionRepoDep,
    frame_store: FrameStoreDep,
    x_confirm_clear_all: str | None = Header(default=None),
) -> Response:
    if x_confirm_clear_all != "yes":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "confirmation_required",
                "message": "clearing all sessions requires confirmation",
                "header": "X-Confirm-Clear-All: yes",
            },
        )
    # Drop frame storage for every known session before wiping the metadata
    # rows — keeping the frame store in sync prevents orphan time-series.
    for s in await session_repo.list_all(limit=10_000):
        await frame_store.delete_session(s.id)
    await session_repo.delete_all()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    session_repo: SessionRepoDep,
    frame_store: FrameStoreDep,
) -> Response:
    # FR-042 idempotent delete: unknown id → 204.
    sid = SessionId(session_id)
    await frame_store.delete_session(sid)
    await session_repo.delete(sid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
