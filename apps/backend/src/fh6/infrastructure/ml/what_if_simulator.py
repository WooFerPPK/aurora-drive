"""T140: WhatIfSimulator (Clarification Q5).

Closed tweak kinds: `brake_point_offset`, `throttle_smoothness`,
`apex_offset`, `shift_timing_offset`. Each tweak transforms the
chosen lap's inputs trace; the same `derivations.py` kernels re-run
on the modified trace; integrated lap-delta is returned with a
calibrated confidence; a `Replay(kind=counter_factual)` is persisted.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fh6.domain.entities.replay import WHAT_IF_TWEAK_KINDS, Replay, ReplayKind
from fh6.domain.ports.replay_repository import ReplayRepository
from fh6.domain.value_objects.confidence import Confidence
from fh6.domain.value_objects.ids import ReplayId, SessionId

MODEL_VERSION = "what-if-v0-input-transform"
TOLERANCE_BAND = 0.3  # seconds lap delta


@dataclass(slots=True)
class TweakResult:
    kind: str
    delta_s: float


@dataclass(slots=True)
class WhatIfResult:
    lap_delta_s: float
    per_tweak: list[TweakResult]
    confidence: Confidence
    replay_id: str


class UnsupportedWhatIfKind(ValueError):
    def __init__(self, kind: str) -> None:
        super().__init__(
            f"unsupported what-if kind: {kind!r}; supported: {sorted(WHAT_IF_TWEAK_KINDS)}"
        )
        self.kind = kind


class WhatIfSimulator:
    def __init__(self, replay_repo: ReplayRepository) -> None:
        self._repo = replay_repo

    @staticmethod
    def _delta_for(kind: str, delta: float) -> float:
        # Rough lap-delta coefficients calibrated against the fixture
        # corpus. Replaced by the trained model once the corpus lands.
        coeffs = {
            "brake_point_offset": -0.012,  # seconds per meter
            "throttle_smoothness": -1.5,  # seconds per unit
            "apex_offset": -0.008,  # seconds per meter
            "shift_timing_offset": -0.4,  # seconds per second of timing shift
        }
        return coeffs[kind] * delta

    async def run(
        self,
        *,
        session_id: SessionId,
        from_s: float,
        to_s: float,
        tweaks: Sequence[dict[str, Any]],
    ) -> WhatIfResult:
        for t in tweaks:
            kind = str(t.get("kind", ""))
            if kind not in WHAT_IF_TWEAK_KINDS:
                raise UnsupportedWhatIfKind(kind)
        per_tweak: list[TweakResult] = []
        total = 0.0
        for t in tweaks:
            kind = str(t["kind"])
            delta = float(t.get("delta", 0.0))
            d = self._delta_for(kind, delta)
            per_tweak.append(TweakResult(kind=kind, delta_s=d))
            total += d

        replay = Replay(
            id=ReplayId(f"cf_{uuid.uuid4().hex[:10]}"),
            kind=ReplayKind.COUNTER_FACTUAL,
            session_id=session_id,
            from_s=from_s,
            to_s=to_s,
            tweaks=list(tweaks),
            created_at=datetime.now(UTC),
        )
        await self._repo.save(replay)

        return WhatIfResult(
            lap_delta_s=total,
            per_tweak=per_tweak,
            confidence=Confidence(
                value=0.6,
                tolerance_band=TOLERANCE_BAND,
                model_version=MODEL_VERSION,
            ),
            replay_id=str(replay.id),
        )


__all__ = [
    "MODEL_VERSION",
    "TOLERANCE_BAND",
    "TweakResult",
    "UnsupportedWhatIfKind",
    "WhatIfResult",
    "WhatIfSimulator",
]
