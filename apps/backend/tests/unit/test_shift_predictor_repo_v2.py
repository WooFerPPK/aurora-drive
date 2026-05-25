"""Unit tests for the v2 surfaces on InMemoryShiftPredictorRepo.

Covers the four methods added by Task 2's port extension:
- upsert_transmission_mode / read_transmission_mode (round-trip + replace-in-place)
- read_transmission_mode (None for unknown fingerprint)
- delete_transmission_mode (1 / 0 rowcount semantics)
- list_fingerprints_for_class_key (engine-curves aggregation,
  candidate-set filter, caller-side paused-filter)

asyncio_mode = "auto" is set in pyproject.toml — async tests run
automatically without explicit marks.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fh6.domain.ports.shift_predictor_repo import (
    BinRecord,
    TransmissionModeRecord,
)
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint
from tests.contract.fake_repos import InMemoryShiftPredictorRepo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 5, 23, 10, 0, 0, tzinfo=UTC)

# Three fingerprints sharing a class key (same num_cylinders=6 + same caller-supplied
# candidate set models the contract — engine_curves itself isn't keyed on class key).
_FP_A = EngineFingerprint(car_ordinal=1001, performance_index=800, num_cylinders=6)
_FP_B = EngineFingerprint(car_ordinal=1002, performance_index=810, num_cylinders=6)
_FP_C = EngineFingerprint(car_ordinal=1003, performance_index=820, num_cylinders=6)

_UNKNOWN_FP = EngineFingerprint(car_ordinal=9999, performance_index=999, num_cylinders=8)


def _bin(fp: EngineFingerprint, gear: int, rpm_bin: int, *, count: int) -> BinRecord:
    return BinRecord(
        fingerprint=fp,
        gear=gear,
        rpm_bin=rpm_bin,
        count=count,
        mean_torque_nm=280.0,
        m2_torque=500.0,
        q90_torque_nm=300.0,
        mean_boost_psi=8.0,
        last_updated=_NOW,
    )


def _mode(
    fp: EngineFingerprint,
    *,
    mode: str = "auto",
    confidence: float = 0.9,
    sample_count: int = 42,
    last_updated: datetime = _NOW,
) -> TransmissionModeRecord:
    return TransmissionModeRecord(
        fingerprint=fp,
        mode=mode,
        confidence=confidence,
        sample_count=sample_count,
        last_updated=last_updated,
    )


# ---------------------------------------------------------------------------
# 1. upsert + read round-trip
# ---------------------------------------------------------------------------


async def test_upsert_transmission_mode_round_trip() -> None:
    repo = InMemoryShiftPredictorRepo()
    rec = _mode(_FP_A, mode="manual", confidence=0.91, sample_count=128)

    await repo.upsert_transmission_mode(rec)
    result = await repo.read_transmission_mode(_FP_A)

    assert result == rec


# ---------------------------------------------------------------------------
# 2. Repeated upsert on same fingerprint replaces in place (PK = fp)
# ---------------------------------------------------------------------------


async def test_upsert_transmission_mode_replaces_in_place() -> None:
    repo = InMemoryShiftPredictorRepo()
    later = datetime(2026, 5, 23, 11, 0, 0, tzinfo=UTC)

    await repo.upsert_transmission_mode(_mode(_FP_A, mode="auto", confidence=0.6, sample_count=10))
    await repo.upsert_transmission_mode(
        _mode(
            _FP_A,
            mode="manual",
            confidence=0.95,
            sample_count=200,
            last_updated=later,
        )
    )

    result = await repo.read_transmission_mode(_FP_A)
    assert result is not None
    assert result.mode == "manual"
    assert result.confidence == 0.95
    assert result.sample_count == 200
    assert result.last_updated == later


# ---------------------------------------------------------------------------
# 3. read_transmission_mode returns None for unknown fingerprint
# ---------------------------------------------------------------------------


async def test_read_transmission_mode_unknown_returns_none() -> None:
    repo = InMemoryShiftPredictorRepo()
    # Seed a different fingerprint so the store isn't empty (defensive).
    await repo.upsert_transmission_mode(_mode(_FP_A))

    result = await repo.read_transmission_mode(_UNKNOWN_FP)
    assert result is None


# ---------------------------------------------------------------------------
# 4. delete_transmission_mode returns 1 on hit, 0 on miss
# ---------------------------------------------------------------------------


async def test_delete_transmission_mode_rowcounts() -> None:
    repo = InMemoryShiftPredictorRepo()
    await repo.upsert_transmission_mode(_mode(_FP_A))

    # Hit returns 1 and removes the row.
    deleted = await repo.delete_transmission_mode(_FP_A)
    assert deleted == 1
    assert await repo.read_transmission_mode(_FP_A) is None

    # Subsequent delete on now-missing key returns 0.
    deleted_again = await repo.delete_transmission_mode(_FP_A)
    assert deleted_again == 0

    # Delete on a never-existed key returns 0.
    deleted_unknown = await repo.delete_transmission_mode(_UNKNOWN_FP)
    assert deleted_unknown == 0


# ---------------------------------------------------------------------------
# 5. list_fingerprints_for_class_key filters by min_total_samples
# ---------------------------------------------------------------------------


async def test_list_fingerprints_for_class_key_filters_below_threshold() -> None:
    repo = InMemoryShiftPredictorRepo()

    # FP_A: 600 + 400 = 1000 total counts → qualifies (>= 1000).
    await repo.upsert_bin(_bin(_FP_A, gear=2, rpm_bin=4000, count=600))
    await repo.upsert_bin(_bin(_FP_A, gear=3, rpm_bin=5500, count=400))

    # FP_B: 1200 total → qualifies.
    await repo.upsert_bin(_bin(_FP_B, gear=2, rpm_bin=4000, count=700))
    await repo.upsert_bin(_bin(_FP_B, gear=3, rpm_bin=5500, count=500))

    # FP_C: 500 total → below threshold.
    await repo.upsert_bin(_bin(_FP_C, gear=2, rpm_bin=4000, count=300))
    await repo.upsert_bin(_bin(_FP_C, gear=3, rpm_bin=5500, count=200))

    result = await repo.list_fingerprints_for_class_key(
        candidate_fingerprints=[_FP_A, _FP_B, _FP_C],
        min_total_samples=1000,
    )

    returned_fps = {fp for fp, _total in result}
    assert returned_fps == {_FP_A, _FP_B}

    # Totals reported should match the SUM(count).
    totals = {fp: total for fp, total in result}
    assert totals[_FP_A] == 1000
    assert totals[_FP_B] == 1200


# ---------------------------------------------------------------------------
# 6. Caller-side paused-fingerprint filter via candidate omission
# ---------------------------------------------------------------------------


async def test_list_fingerprints_for_class_key_caller_excludes_paused() -> None:
    repo = InMemoryShiftPredictorRepo()

    # Same seed as scenario 5 — all three fingerprints have rows.
    await repo.upsert_bin(_bin(_FP_A, gear=2, rpm_bin=4000, count=600))
    await repo.upsert_bin(_bin(_FP_A, gear=3, rpm_bin=5500, count=400))
    await repo.upsert_bin(_bin(_FP_B, gear=2, rpm_bin=4000, count=700))
    await repo.upsert_bin(_bin(_FP_B, gear=3, rpm_bin=5500, count=500))
    await repo.upsert_bin(_bin(_FP_C, gear=2, rpm_bin=4000, count=300))
    await repo.upsert_bin(_bin(_FP_C, gear=3, rpm_bin=5500, count=200))

    # Caller pre-filters _FP_B out of the candidate set (simulates the paused-set
    # filter that ShiftPredictor.flush() does in Task 6). _FP_C is also below
    # threshold so should drop on its own merits.
    result = await repo.list_fingerprints_for_class_key(
        candidate_fingerprints=[_FP_A, _FP_C],
        min_total_samples=1000,
    )

    returned_fps = {fp for fp, _total in result}
    assert _FP_B not in returned_fps
    assert returned_fps == {_FP_A}


# ---------------------------------------------------------------------------
# 7. Empty candidate set short-circuits to []
# ---------------------------------------------------------------------------


async def test_list_fingerprints_for_class_key_empty_candidates() -> None:
    repo = InMemoryShiftPredictorRepo()
    await repo.upsert_bin(_bin(_FP_A, gear=2, rpm_bin=4000, count=2000))

    result = await repo.list_fingerprints_for_class_key(
        candidate_fingerprints=[],
        min_total_samples=1,
    )
    assert result == []
