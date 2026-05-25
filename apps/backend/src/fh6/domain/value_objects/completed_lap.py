from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CompletedLap:
    """A recorded lap within a session.

    lap_number is 0-indexed (first lap = 0), matching the Rust reference.
    lap_time_s is the peak currentLapS reached during that lap cycle.
    """

    lap_number: int
    lap_time_s: float
