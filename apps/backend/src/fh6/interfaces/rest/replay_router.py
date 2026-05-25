"""T116: `/api/replay/:id` router (API spec §9)."""

from __future__ import annotations

from fastapi import APIRouter

from fh6.domain.value_objects.ids import ReplayId
from fh6.interfaces.dependencies import ReplayRepoDep
from fh6.interfaces.rest.errors import not_found
from fh6.interfaces.rest.schemas.replay import ReplayResponse

router = APIRouter()


@router.get("/{replay_id}", response_model=ReplayResponse, response_model_by_alias=True)
async def get_replay(replay_id: str, replay_repo: ReplayRepoDep) -> ReplayResponse:
    rep = await replay_repo.get(ReplayId(replay_id))
    if rep is None:
        raise not_found(f"replay {replay_id!r} not found", resource="replay")
    return ReplayResponse(
        id=str(rep.id),
        kind=rep.kind.value,
        sessionId=str(rep.session_id),
        fromS=rep.from_s,
        toS=rep.to_s,
        frames=rep.frames,
        annotations=rep.annotations,
        tweaks=rep.tweaks,
        createdAt=rep.created_at,
    )
