"""`/health/telemetry` — surfaces UDP listener bind status."""

from __future__ import annotations

from fastapi import APIRouter

from fh6.interfaces.dependencies import TelemetryHealthDep

router = APIRouter()


@router.get("/telemetry")
async def get_telemetry_health(health: TelemetryHealthDep) -> dict[str, object]:
    return {
        "listening": health.listening,
        "host": health.host,
        "port": health.port,
        "bind_error": health.bind_error,
        "last_packet_at": (
            health.last_packet_at.isoformat() if health.last_packet_at is not None else None
        ),
    }
