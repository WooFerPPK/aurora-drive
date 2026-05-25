"""T110: AskCoach use case.

Extracts the cited session's relevant telemetry windows, builds the
prompt from `qa.txt`, and streams the response from the LLM port.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from fh6.domain.ports.frame_store import FrameStore
from fh6.domain.ports.llm_port import LLMPort, LLMRequest
from fh6.domain.ports.session_repository import SessionRepository
from fh6.domain.value_objects.ids import SessionId


@dataclass(slots=True)
class AskCoachRequest:
    session_id: SessionId
    question: str


class AskCoach:
    def __init__(
        self,
        *,
        sessions: SessionRepository,
        frames: FrameStore,
        llm: LLMPort,
    ) -> None:
        self._sessions = sessions
        self._frames = frames
        self._llm = llm

    async def __call__(self, request: AskCoachRequest) -> AsyncIterator[str]:
        session = await self._sessions.get(request.session_id)
        if session is None:
            raise LookupError(f"session {request.session_id!r} not found")

        projection = await self._frames.read_projection(
            request.session_id,
            hz=10,
            fields=("speed", "throttle", "brake"),
        )
        data = projection.get("data") or []
        # Compress into a tiny summary the prompt can reference.
        window_summary = (
            f"{len(data)} frames @ 10Hz; "
            f"top speed={session.top_speed_mps:.1f} m/s; "
            f"best lap={session.best_lap_s}s"
        )
        context: dict[str, object] = {
            "session_id": str(request.session_id),
            "session_summary": (
                f"car={session.car_id} type={session.type.value} laps={session.lap_count}"
            ),
            "relevant_windows": window_summary,
            "lap_aggregates": f"lap_count={session.lap_count}",
            "question": request.question,
        }
        return self._llm.stream_answer(LLMRequest(template_name="qa", context=context))
