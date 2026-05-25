"""T070: `/api/cars` router (API spec §4)."""

from __future__ import annotations

from fastapi import APIRouter, Header, status
from fastapi.responses import Response

from fh6.application.use_cases.get_live_aggregate_for_car import (
    GetLiveAggregateForCar,
)
from fh6.domain.value_objects.ids import CarId
from fh6.interfaces.dependencies import CarRepoDep, SessionRepoDep
from fh6.interfaces.rest.errors import confirm_required, not_found
from fh6.interfaces.rest.schemas.cars import (
    CarAggregateResponse,
    CarListResponse,
    CarRenameRequest,
    CarRenameResponse,
    CarSummary,
)

router = APIRouter()


@router.get("", response_model=CarListResponse, response_model_by_alias=True)
async def list_cars(car_repo: CarRepoDep) -> CarListResponse:
    cars = await car_repo.list_all()
    return CarListResponse(
        cars=[
            CarSummary(
                id=str(c.id),
                display=c.display_name,
                short=c.short_name,
                ordinal=c.car_ordinal,
                carClass=c.car_class,
                pi=c.performance_index,
                drivetrain=c.drivetrain,
                group=c.car_group,
                groupLabel=c.car_group_label,
                lastSeenAt=c.last_seen_at,
                sessionCount=c.session_count,
                totalSecondsDriven=c.total_seconds_driven,
                bestLapByTrack=[],
            )
            for c in cars
        ]
    )


@router.get("/{car_id}/aggregate", response_model=CarAggregateResponse)
async def car_aggregate(
    car_id: str,
    car_repo: CarRepoDep,
    session_repo: SessionRepoDep,
) -> CarAggregateResponse:
    use_case = GetLiveAggregateForCar(car_repo, session_repo)
    agg = await use_case(CarId(car_id))
    if agg is None:
        raise not_found(f"car {car_id!r} not found", resource="car")
    return CarAggregateResponse(
        carId=agg.car_id,
        lapsTotal=agg.laps_total,
        sectorBests=agg.sector_bests,
        perCornerAverages=agg.per_corner_averages,
        shift=agg.shift,
        tirePeakUseByCorner=agg.tire_peak_use_by_corner,
        preferredGearByCorner=agg.preferred_gear_by_corner,
        gripBudgetCeiling=agg.grip_budget_ceiling,
        thisCarSpecificStyle=agg.this_car_specific_style,
    )


@router.patch("/{ordinal}", response_model=CarRenameResponse)
async def rename_car_by_ordinal(
    ordinal: int,
    body: CarRenameRequest,
    car_repo: CarRepoDep,
) -> CarRenameResponse:
    """Crowdsourcing path for car names.

    The bundled ordinal → name table is community-maintained and will
    always lag behind Playground's car-pack drops. When a user sees a
    car named `Car #{ordinal}` they can submit the correct name; we
    stamp every Car row sharing that ordinal so all tunes of the same
    car get fixed at once. The DB row wins over the static lookup for
    subsequent reads (PgCarRepository.upsert no longer overwrites
    display_name on update).
    """
    display_name = body.display_name.strip()
    if not display_name:
        raise not_found(
            f"display_name must be non-empty for ordinal {ordinal}",
            resource="car_ordinal",
        )
    short_name = display_name.split(" ", 1)[-1]
    updated = await car_repo.rename_by_ordinal(
        ordinal, display_name=display_name, short_name=short_name
    )
    if updated == 0:
        raise not_found(
            f"no car with ordinal {ordinal} has been ingested yet",
            resource="car_ordinal",
        )
    return CarRenameResponse(
        ordinal=ordinal,
        displayName=display_name,
        shortName=short_name,
        updated=updated,
    )


@router.delete("/{car_id}/sessions", status_code=status.HTTP_204_NO_CONTENT)
async def delete_car_sessions(car_id: str, car_repo: CarRepoDep) -> Response:
    # Idempotent: deleting unknown car still returns 204.
    await car_repo.delete_all_sessions(CarId(car_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{car_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_car(car_id: str, car_repo: CarRepoDep) -> Response:
    # Idempotent: unknown id still returns 204. Sessions / frames /
    # mistakes for this car cascade via the FK constraints.
    await car_repo.delete(CarId(car_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


data_router = APIRouter()


@data_router.delete("/all", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_data(
    car_repo: CarRepoDep,
    x_confirm: str | None = Header(default=None, alias="X-Confirm"),
) -> Response:
    """`DELETE /api/data/all` (API spec §13). Gated by header X-Confirm.

    Wipes every car (and via FK cascade every session, frame, and
    mistake) so the cars dropdown is truly empty afterwards.
    """
    if (x_confirm or "").lower() != "true":
        raise confirm_required("DELETE /api/data/all requires header X-Confirm: true")
    await car_repo.delete_all()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
