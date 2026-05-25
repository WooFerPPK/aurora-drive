"""T113: post-session insight generator.

MVP scoring is rule-based off session stats; the actual ranked
insight cards are emitted with a `model_version` so the API spec
contract holds, and the `delta_if_fixed_s` field is the rough lap-
time savings estimate the UI shows."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fh6.domain.entities.coach_insight import CoachInsight
from fh6.domain.entities.session import Session
from fh6.domain.ports.coach_repository import CoachRepository


@dataclass(slots=True)
class GenerateInsights:
    coach_repo: CoachRepository

    async def __call__(self, session: Session) -> list[CoachInsight]:
        insights: list[CoachInsight] = []

        if session.lap_count >= 1 and session.best_lap_s is not None:
            insights.append(
                CoachInsight(
                    id=f"i_{uuid.uuid4().hex[:10]}",
                    session_id=session.id,
                    priority="medium",
                    title="Lap consistency",
                    body=(
                        f"You ran {session.lap_count} laps with a best of "
                        f"{session.best_lap_s:.2f}s. Tighten the slowest lap "
                        "for a quick gain."
                    ),
                    tone="tip",
                    actions=["replay"],
                    delta_if_fixed_s=0.5,
                )
            )

        if session.top_speed_mps > 80.0:
            insights.append(
                CoachInsight(
                    id=f"i_{uuid.uuid4().hex[:10]}",
                    session_id=session.id,
                    priority="low",
                    title="Top-speed exposure",
                    body=(
                        f"Top speed {session.top_speed_mps:.1f} m/s — watch "
                        "lift-off oversteer on long straights ending in tight corners."
                    ),
                    tone="info",
                    actions=[],
                    delta_if_fixed_s=None,
                )
            )

        for ins in insights:
            await self.coach_repo.save_insight(ins)
        return insights
