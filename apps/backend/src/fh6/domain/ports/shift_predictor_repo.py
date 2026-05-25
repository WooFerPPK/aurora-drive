"""Port for the shift predictor persistence layer.

Defines the repository Protocol plus the frozen record dataclasses it
operates on. The SQL adapter projects DB rows to/from the three
primary-key columns that make up an EngineFingerprint; the Protocol
itself stays clean and works with value objects.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from fh6.domain.value_objects.engine_fingerprint import EngineClassKey, EngineFingerprint
from fh6.domain.value_objects.ids import SessionId


@dataclass(frozen=True, slots=True)
class BinRecord:
    fingerprint: EngineFingerprint
    gear: int
    rpm_bin: int
    count: int
    mean_torque_nm: float
    m2_torque: float
    q90_torque_nm: float
    mean_boost_psi: float
    last_updated: datetime


@dataclass(frozen=True, slots=True)
class RatioRecord:
    fingerprint: EngineFingerprint
    gear: int
    ratio: float
    variance: float
    last_updated: datetime


@dataclass(frozen=True, slots=True)
class ClassPriorBin:
    class_key: EngineClassKey
    gear: int
    rpm_bin: int
    count: int
    q90_torque_nm: float
    last_built: datetime


@dataclass(frozen=True, slots=True)
class ShiftEventRow:
    id: int | None  # None when not yet persisted
    session_id: SessionId
    fingerprint: EngineFingerprint
    shift_at: datetime
    gear_from: int
    gear_to: int
    actual_rpm: float
    recommended_rpm: float | None
    recommendation_conf: float | None
    predicted_post_torque: float | None
    measured_post_torque: float | None
    est_cost_s: float | None
    # v2 downshift evaluator fields (FR-048). Default to None so the v1
    # upshift evaluator and existing call sites continue to compile.
    post_shift_rpm: float | None = None
    recommended_post_rpm: float | None = None


@dataclass(frozen=True, slots=True)
class ResetCounts:
    engine_curves: int
    gear_ratios: int
    shift_events: int
    transmission_modes: int = 0


@dataclass(frozen=True, slots=True)
class TransmissionModeRecord:
    fingerprint: EngineFingerprint
    mode: str  # "auto" | "manual" | "unknown"
    confidence: float
    sample_count: int
    last_updated: datetime


class ShiftPredictorRepository(Protocol):
    async def upsert_bin(self, rec: BinRecord) -> None: ...
    async def upsert_bins(self, recs: Sequence[BinRecord]) -> None: ...
    async def read_bins(self, fp: EngineFingerprint) -> list[BinRecord]: ...

    async def upsert_ratio(self, rec: RatioRecord) -> None: ...
    async def read_ratios(self, fp: EngineFingerprint) -> list[RatioRecord]: ...

    async def upsert_class_prior_bin(self, rec: ClassPriorBin) -> None: ...
    async def read_class_prior(self, key: EngineClassKey) -> list[ClassPriorBin]: ...
    async def list_fingerprints_for_class_key(
        self,
        *,
        candidate_fingerprints: Sequence[EngineFingerprint],
        min_total_samples: int,
    ) -> list[tuple[EngineFingerprint, int]]:
        """Return the subset of `candidate_fingerprints` whose total engine_curves
        `count` meets `min_total_samples`, paired with that total.

        The caller is responsible for supplying class-key-matching candidates —
        `engine_curves` does not store the class key (which is `(carClass,
        carGroup, drivetrainType, numCylinders)`), so a DB-side filter on the
        full key isn't possible. `ShiftPredictor` knows the class-key-of-fingerprint
        mapping from its session state and passes the matching set in."""
        ...

    async def record_shift_event(self, row: ShiftEventRow) -> None: ...
    async def read_shift_events(self, session_id: SessionId) -> list[ShiftEventRow]: ...

    async def reset_fingerprint(self, fp: EngineFingerprint) -> ResetCounts: ...

    async def upsert_transmission_mode(self, rec: TransmissionModeRecord) -> None: ...
    async def read_transmission_mode(
        self, fp: EngineFingerprint
    ) -> TransmissionModeRecord | None: ...
    async def delete_transmission_mode(self, fp: EngineFingerprint) -> int: ...
