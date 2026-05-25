"""Postgres-backed `DriverRepository`.

The local-first deployment has a single driver per install, so the
table holds exactly one row keyed `id='local'`. `get()` returns the
default empty `DriverProfile` when the row is absent, matching the
`_InMemoryDriverRepository` contract; `save()` upserts.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fh6.domain.entities.driver_profile import DriverProfile
from fh6.infrastructure.db.models.driver import DriverProfileModel

_PROFILE_ID = "local"


class PgDriverRepository:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sm = sessionmaker

    @staticmethod
    def _to_domain(row: DriverProfileModel) -> DriverProfile:
        return DriverProfile(
            laps_analyzed=row.laps_analyzed,
            distance_analyzed_m=row.distance_analyzed_m,
            seconds_analyzed=row.seconds_analyzed,
            fingerprint=dict(row.fingerprint or {}),
            fingerprint_baseline_90d=dict(row.fingerprint_baseline_90d or {}),
            traits=list(row.traits or []),
            strengths=list(row.strengths or []),
            weaknesses=list(row.weaknesses or []),
            car_agnostic_share=row.car_agnostic_share,
            persona=row.persona,
            persona_updated_at=row.persona_updated_at,
            model_version=row.model_version,
        )

    async def get(self) -> DriverProfile:
        async with self._sm() as db:
            row = await db.get(DriverProfileModel, _PROFILE_ID)
            return self._to_domain(row) if row is not None else DriverProfile()

    async def save(self, profile: DriverProfile) -> None:
        async with self._sm() as db:
            row = await db.get(DriverProfileModel, _PROFILE_ID)
            if row is None:
                row = DriverProfileModel(id=_PROFILE_ID)
                db.add(row)
            row.laps_analyzed = profile.laps_analyzed
            row.distance_analyzed_m = profile.distance_analyzed_m
            row.seconds_analyzed = profile.seconds_analyzed
            row.fingerprint = dict(profile.fingerprint)
            row.fingerprint_baseline_90d = dict(profile.fingerprint_baseline_90d)
            row.traits = list(profile.traits)
            row.strengths = list(profile.strengths)
            row.weaknesses = list(profile.weaknesses)
            row.car_agnostic_share = profile.car_agnostic_share
            row.persona = profile.persona
            row.persona_updated_at = profile.persona_updated_at
            row.model_version = profile.model_version
            await db.commit()
