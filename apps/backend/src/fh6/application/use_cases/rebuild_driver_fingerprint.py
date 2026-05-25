"""T151: rebuild the driver fingerprint over all sessions.

Idempotent. Called nightly by cron + on-demand from the driver router.
The global profile aggregates ALL sessions (free-roam dominates because
free-roam is the bulk of captured data). Per-session profiles use the
same model with a single-session input — see `BuildSessionDriverProfile`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from fh6.domain.entities.driver_profile import DriverProfile
from fh6.domain.entities.session import Session
from fh6.domain.ports.car_repository import CarRepository
from fh6.domain.ports.driver_repository import DriverRepository
from fh6.domain.ports.session_repository import SessionRepository
from fh6.infrastructure.ml.driver_fingerprint.baseline import (
    DriverFingerprintModel,
    FingerprintResult,
)


def _build_profile(result: FingerprintResult) -> DriverProfile:
    """Translate raw model output into the wire-ready profile.

    Cosmetic fields (traits/strengths/weaknesses/persona) are only
    populated once there is enough data. Below that threshold the
    profile stays well-shaped but empty so the frontend can show a
    proper "drive more" empty state.
    """
    if not result.has_data:
        return DriverProfile(
            laps_analyzed=result.laps_analyzed,
            distance_analyzed_m=result.distance_analyzed_m,
            seconds_analyzed=result.seconds_analyzed,
            fingerprint=result.fingerprint,
            fingerprint_baseline_90d=result.fingerprint,
            traits=[],
            strengths=[],
            weaknesses=[],
            car_agnostic_share=0.0,
            persona="",
            persona_updated_at=None,
            model_version=result.confidence.model_version,
        )

    strengths = [k for k, v in result.fingerprint.items() if v >= 0.7]
    weaknesses = [k for k, v in result.fingerprint.items() if v <= 0.35]
    traits = [
        {"id": k, "name": k.title(), "score": v, "blurb": f"{k} = {v:.2f}"}
        for k, v in result.fingerprint.items()
    ]
    patient = result.fingerprint.get("patient", 0.0)
    smooth = result.fingerprint.get("smooth", 0.0)
    brave = result.fingerprint.get("brave", 0.0)
    if patient >= 0.6 and smooth >= 0.6:
        persona = "Patient stylist"
    elif brave >= 0.7:
        persona = "Aggressive sprinter"
    else:
        persona = "Balanced cruiser"

    return DriverProfile(
        laps_analyzed=result.laps_analyzed,
        distance_analyzed_m=result.distance_analyzed_m,
        seconds_analyzed=result.seconds_analyzed,
        fingerprint=result.fingerprint,
        fingerprint_baseline_90d=result.fingerprint,
        traits=traits,
        strengths=strengths,
        weaknesses=weaknesses,
        car_agnostic_share=0.5,
        persona=persona,
        persona_updated_at=datetime.now(UTC),
        model_version=result.confidence.model_version,
    )


@dataclass(slots=True)
class RebuildDriverFingerprint:
    drivers: DriverRepository
    cars: CarRepository
    sessions: SessionRepository

    async def __call__(self) -> DriverProfile:
        all_sessions: list[Session] = []
        for car in await self.cars.list_all():
            all_sessions.extend(await self.sessions.list_for_car(car.id, limit=10_000))
        model = DriverFingerprintModel()
        result = model.fit(all_sessions)
        profile = _build_profile(result)
        await self.drivers.save(profile)
        return profile


@dataclass(slots=True)
class BuildSessionDriverProfile:
    """Per-session driver profile — no persistence."""

    sessions: SessionRepository

    async def __call__(self, session: Session | Sequence[Session]) -> DriverProfile:
        sessions: list[Session] = [session] if isinstance(session, Session) else list(session)
        model = DriverFingerprintModel()
        result = model.fit(sessions)
        return _build_profile(result)
