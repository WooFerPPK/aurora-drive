from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fh6.infrastructure.db.models.settings import SettingsRowModel

# Per spec.md FR-039a + Clarification Q2 + research R-4.
# Per spec.md FR-039 + constitution Principle II → shareAnalytics OFF by default.
DEFAULT_SETTINGS: dict[str, Any] = {
    "telemetry": {
        "listenAddr": "127.0.0.1",
        "listenPort": 5302,
        "gameProfile": "fh6",
        "autoDetectCadence": True,
        "preferredFrameRate": 30,
    },
    "models": {
        "llmCoach": True,
        "tireWearModel": True,
        "shiftCoach": True,
        "predictions": True,
        "drivingFingerprint": True,
        "voiceCallouts": False,
        "minCoachPriority": "tip",
    },
    "data": {
        "recordSessions": True,
        "storeRawPackets": False,
        "retentionDays": 90,
        "shareAnalytics": False,
        # Clarification Q2 / research R-4: 5 GB per car default.
        "maxBytesPerCar": 5_368_709_120,
    },
    "display": {
        "speedUnit": "kmh",
        "tempUnit": "c",
        "reduceMotion": False,
        "theme": "dark",
    },
    # world_map widget calibration. Seeded with the fh6-tel Japan preset so
    # the widget lines up against the bundled tile pyramid out of the box.
    # Users re-run the calibration UI for the real FH6 map; PATCH replaces
    # the whole `calibration` sub-object.
    "worldMap": {
        "calibration": {
            "aWorld": [-119.49154, 3888.595],
            "aPix": [2089486.0, 2087415.0],
            "bWorld": [-7104.7695, -1863.08],
            "bPix": [2086885.0, 2089556.0],
        },
    },
    "perCarOverrides": [],
}


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in patch.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class PgSettingsRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    async def seed_defaults_if_empty(self) -> None:
        # Misnomer kept for the existing app.py call site. We backfill any
        # top-level group missing from the table (new groups added in a
        # later release on an existing install) without disturbing values
        # the user has already changed.
        async with self._sm() as db:
            rows = (await db.execute(select(SettingsRowModel))).scalars().all()
            present = {r.key for r in rows}
            missing = [k for k in DEFAULT_SETTINGS if k not in present]
            if not missing:
                return
            now = datetime.now(UTC)
            for key in missing:
                db.add(SettingsRowModel(key=key, value=DEFAULT_SETTINGS[key], updated_at=now))
            await db.commit()

    async def get_all(self) -> dict[str, Any]:
        async with self._sm() as db:
            rows = (await db.execute(select(SettingsRowModel))).scalars().all()
            return {row.key: row.value for row in rows}

    async def get_group(self, key: str) -> dict[str, Any]:
        async with self._sm() as db:
            row = await db.get(SettingsRowModel, key)
            if row is None:
                return dict(DEFAULT_SETTINGS.get(key, {}))
            return dict(row.value)

    async def patch(self, partial: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC)
        async with self._sm() as db:
            for key, sub in partial.items():
                if not isinstance(sub, (dict, list)):
                    raise ValueError(f"settings group {key!r} must be object or list")
                row = await db.get(SettingsRowModel, key)
                if row is None:
                    db.add(SettingsRowModel(key=key, value=sub, updated_at=now))
                elif isinstance(sub, dict):
                    row.value = _deep_merge(dict(row.value or {}), sub)
                    row.updated_at = now
                else:
                    row.value = sub
                    row.updated_at = now
            await db.commit()
        return await self.get_all()
