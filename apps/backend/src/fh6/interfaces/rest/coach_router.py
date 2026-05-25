"""T094 / T112 / T114: `/api/coach` router (API spec §7 + Clarification Q3)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from fh6.application.use_cases.ask_coach import AskCoach, AskCoachRequest
from fh6.application.use_cases.create_telemetry_clip_replay import (
    CreateTelemetryClipReplay,
)
from fh6.application.use_cases.generate_insights import GenerateInsights
from fh6.domain.value_objects.ids import SessionId
from fh6.interfaces.dependencies import (
    CoachAvailabilityDep,
    CoachRepoDep,
    FrameStoreDep,
    LLMDep,
    ReplayRepoDep,
    SessionRepoDep,
)
from fh6.interfaces.rest.errors import not_found
from fh6.interfaces.rest.schemas.coach import (
    CoachAskRequest,
    CoachStatus,
    InsightCard,
    InsightsResponse,
)

router = APIRouter()


@router.get("/status", response_model=CoachStatus)
async def coach_status(availability: CoachAvailabilityDep) -> CoachStatus:
    """API spec §7 + Clarification Q3 `/api/coach/status`."""
    av = await availability.status()
    return CoachStatus(available=av.available, reason=av.reason, model=av.model)


@router.get("/insights", response_model=InsightsResponse)
async def list_insights(sessionId: str, coach_repo: CoachRepoDep) -> InsightsResponse:
    rows = await coach_repo.list_insights(SessionId(sessionId))
    return InsightsResponse(
        insights=[
            InsightCard(
                id=r.id,
                sessionId=str(r.session_id),
                priority=r.priority,
                title=r.title,
                body=r.body,
                tone=r.tone,
                actions=r.actions,
                deltaIfFixedS=r.delta_if_fixed_s,
                replayId=str(r.replay_id) if r.replay_id else None,
            )
            for r in rows
        ]
    )


@router.post("/insights/{insight_id}/dismiss", status_code=204)
async def dismiss_insight(insight_id: str, coach_repo: CoachRepoDep) -> None:
    # Idempotent: dismissing an already-dismissed insight returns 204 too.
    await coach_repo.dismiss_insight(insight_id)


@router.post("/insights/{insight_id}/replay")
async def replay_insight(
    insight_id: str,
    coach_repo: CoachRepoDep,
    frame_store: FrameStoreDep,
    replay_repo: ReplayRepoDep,
) -> dict[str, str]:
    """T115/T116: build a `Replay(kind=telemetry_clip)` from the insight's
    cited window."""
    insight = await coach_repo.get_insight(insight_id)
    if insight is None:
        raise not_found(f"insight {insight_id!r} not found", resource="insight")

    # Citation-window TODO: the [from_s, to_s] window should come from the
    # insight's cite payload; until that's encoded, fall back to a fixed
    # 10s clip starting from the session origin.
    use_case = CreateTelemetryClipReplay(
        frame_store=frame_store,
        replay_repo=replay_repo,
    )
    replay = await use_case(
        session_id=insight.session_id,
        from_s=0.0,
        to_s=10.0,
    )
    return {"replayId": str(replay.id)}


@router.post("/ask")
async def ask(
    payload: CoachAskRequest,
    session_repo: SessionRepoDep,
    frame_store: FrameStoreDep,
    llm: LLMDep,
) -> StreamingResponse:
    """T112: stream the AskCoach output as chunked transfer-encoded."""
    use_case = AskCoach(sessions=session_repo, frames=frame_store, llm=llm)
    try:
        stream = await use_case(
            AskCoachRequest(
                session_id=SessionId(payload.sessionId),
                question=payload.question,
            )
        )
    except LookupError as exc:
        raise not_found(str(exc), resource="session") from exc

    async def _body() -> AsyncIterator[bytes]:
        async for chunk in stream:
            yield chunk.encode("utf-8")

    return StreamingResponse(_body(), media_type="text/event-stream")


@router.post("/insights/{session_id}/generate", status_code=201)
async def generate_for_session(
    session_id: str,
    session_repo: SessionRepoDep,
    coach_repo: CoachRepoDep,
) -> dict[str, int]:
    session = await session_repo.get(SessionId(session_id))
    if session is None:
        raise not_found(f"session {session_id!r} not found", resource="session")
    use_case = GenerateInsights(coach_repo=coach_repo)
    insights = await use_case(session)
    return {"generated": len(insights)}
