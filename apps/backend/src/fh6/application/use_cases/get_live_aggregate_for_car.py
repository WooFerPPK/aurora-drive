"""T071: GetLiveAggregateForCar.

Computes per-car aggregates at read time over the per-car sessions
(constitution Principle V — aggregates never replace per-session
storage). MVP returns the shape with simple roll-ups from the session
list; per-corner / preferred-gear data is filled when the corner-
detection step lands (track inference depth in US5/US6).
"""

from __future__ import annotations

from dataclasses import dataclass

from fh6.domain.ports.car_repository import CarRepository
from fh6.domain.ports.session_repository import SessionRepository
from fh6.domain.value_objects.ids import CarId


@dataclass(slots=True)
class CarAggregate:
    car_id: str
    laps_total: int
    grip_budget_ceiling: float
    sector_bests: list[dict[str, float]]
    per_corner_averages: list[dict[str, object]]
    shift: dict[str, float]
    tire_peak_use_by_corner: list[dict[str, object]]
    preferred_gear_by_corner: list[dict[str, object]]
    this_car_specific_style: dict[str, float]


class GetLiveAggregateForCar:
    def __init__(
        self,
        car_repo: CarRepository,
        session_repo: SessionRepository,
    ) -> None:
        self._cars = car_repo
        self._sessions = session_repo

    async def __call__(self, car_id: CarId) -> CarAggregate | None:
        car = await self._cars.get(car_id)
        if car is None:
            return None
        sessions = await self._sessions.list_for_car(car_id, limit=1000)
        laps_total = sum(s.lap_count for s in sessions)
        best_lap = min(
            (s.best_lap_s for s in sessions if s.best_lap_s is not None),
            default=None,
        )
        # Grip-budget ceiling: max derived gripBudgetUsed across the
        # corpus would require a frame scan; MVP uses 1.0 (full budget
        # observed) when any closed session exists, else 0.
        grip_ceiling = 1.0 if any(s.ended_at for s in sessions) else 0.0
        sector_bests: list[dict[str, float]] = (
            [{"sector": 0, "bestS": best_lap}] if best_lap is not None else []
        )
        return CarAggregate(
            car_id=str(car_id),
            laps_total=laps_total,
            grip_budget_ceiling=grip_ceiling,
            sector_bests=sector_bests,
            per_corner_averages=[],
            shift={},
            tire_peak_use_by_corner=[],
            preferred_gear_by_corner=[],
            this_car_specific_style={},
        )
