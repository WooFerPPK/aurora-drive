"""Offline track inference via DBSCAN clustering over accumulated
position traces (research R-11). Persists `tracks` rows with
`inferred=true`; reserved `confirmed_name`/`confirmed_at` columns
remain null in MVP. A future endpoint `POST /api/track/confirm` will
flip these.

This module is intentionally small in MVP; the live request
`/api/track/current` returns the matched cluster (or a synthetic
`open_world` cluster if none exist).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class InferredTrack:
    id: str
    display_name: str
    inferred: bool = True
    outline: list[tuple[float, float]] | None = None
    corners: list[dict[str, object]] | None = None


def open_world_default() -> InferredTrack:
    return InferredTrack(
        id="open_world",
        display_name="Open world",
        inferred=True,
        outline=[],
        corners=[],
    )


def cluster_positions(
    positions: list[tuple[float, float]],
    *,
    eps: float = 50.0,
    min_samples: int = 30,
) -> list[InferredTrack]:
    """DBSCAN clustering stub. Full sklearn implementation lands in
    US5/US6 model work. MVP returns one synthetic cluster covering all
    points so `/api/track/current` can return a non-empty result while
    the real model is offline.
    """
    if not positions:
        return []
    return [
        InferredTrack(
            id="track_inferred_1",
            display_name="Inferred track 1",
            inferred=True,
            outline=positions[:: max(1, len(positions) // 64)],
            corners=[],
        )
    ]
