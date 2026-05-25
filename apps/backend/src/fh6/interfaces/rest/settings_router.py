"""T160 / T161: `/api/settings` (API spec §10)."""

from __future__ import annotations

from fastapi import APIRouter

from fh6.interfaces.dependencies import SettingsRepoDep
from fh6.interfaces.rest.errors import validation_error_400
from fh6.interfaces.rest.schemas.settings import SettingsPatch, SettingsResponse

router = APIRouter()

# Constitution / FR-005 — port range refusal.
FORBIDDEN_PORT_LO = 5200
FORBIDDEN_PORT_HI = 5300
MAX_BYTES_FLOOR = 100_000_000  # research R-4 / contracts/10-settings.md


def _validate_patch(patch: SettingsPatch) -> None:
    if patch.telemetry is not None:
        port = patch.telemetry.listenPort
        if FORBIDDEN_PORT_LO <= port <= FORBIDDEN_PORT_HI:
            raise validation_error_400(
                f"listenPort {port} is in FH6 reserved range "
                f"[{FORBIDDEN_PORT_LO}, {FORBIDDEN_PORT_HI}]",
                field="telemetry.listenPort",
            )
    if patch.data is not None:
        cap = patch.data.maxBytesPerCar
        if cap < MAX_BYTES_FLOOR:
            raise validation_error_400(
                f"maxBytesPerCar {cap} < floor {MAX_BYTES_FLOOR}",
                field="data.maxBytesPerCar",
            )


@router.get("", response_model=SettingsResponse)
async def get_settings(settings_repo: SettingsRepoDep) -> SettingsResponse:
    all_groups = await settings_repo.get_all()
    return SettingsResponse(**all_groups)


@router.patch("", response_model=SettingsResponse)
async def patch_settings(
    body: SettingsPatch,
    settings_repo: SettingsRepoDep,
) -> SettingsResponse:
    _validate_patch(body)
    partial = body.model_dump(exclude_none=True)
    merged = await settings_repo.patch(partial)
    return SettingsResponse(**merged)
