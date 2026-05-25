"""Unit tests for InMemoryShiftPredictorRepo.

Verifies the in-memory fake behaves correctly so the production
Postgres adapter can be validated against the same contract later.

asyncio_mode = "auto" is set in pyproject.toml — all async tests
run automatically without explicit marks.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fh6.domain.ports.shift_predictor_repo import (
    BinRecord,
    ClassPriorBin,
    RatioRecord,
    ShiftEventRow,
)
from fh6.domain.value_objects.engine_fingerprint import EngineClassKey, EngineFingerprint
from fh6.domain.value_objects.ids import SessionId
from tests.contract.fake_repos import InMemoryShiftPredictorRepo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FP = EngineFingerprint(car_ordinal=2451, performance_index=812, num_cylinders=6)
_FP2 = EngineFingerprint(car_ordinal=9999, performance_index=700, num_cylinders=4)
_NOW = datetime(2026, 5, 23, 10, 0, 0, tzinfo=UTC)


def _bin(
    fp: EngineFingerprint, gear: int, rpm_bin: int, *, count: int = 1, q90: float = 300.0
) -> BinRecord:
    return BinRecord(
        fingerprint=fp,
        gear=gear,
        rpm_bin=rpm_bin,
        count=count,
        mean_torque_nm=280.0,
        m2_torque=500.0,
        q90_torque_nm=q90,
        mean_boost_psi=8.0,
        last_updated=_NOW,
    )


def _ratio(fp: EngineFingerprint, gear: int, *, ratio: float = 3.5) -> RatioRecord:
    return RatioRecord(
        fingerprint=fp,
        gear=gear,
        ratio=ratio,
        variance=0.01,
        last_updated=_NOW,
    )


def _class_prior(key: EngineClassKey, gear: int, rpm_bin: int) -> ClassPriorBin:
    return ClassPriorBin(
        class_key=key,
        gear=gear,
        rpm_bin=rpm_bin,
        count=10,
        q90_torque_nm=250.0,
        last_built=_NOW,
    )


def _shift_event(
    session_id: SessionId,
    fp: EngineFingerprint,
    *,
    shift_at: datetime = _NOW,
    id: int | None = None,
) -> ShiftEventRow:
    return ShiftEventRow(
        id=id,
        session_id=session_id,
        fingerprint=fp,
        shift_at=shift_at,
        gear_from=2,
        gear_to=3,
        actual_rpm=6800.0,
        recommended_rpm=6500.0,
        recommendation_conf=0.85,
        predicted_post_torque=310.0,
        measured_post_torque=305.0,
        est_cost_s=0.05,
    )


# ---------------------------------------------------------------------------
# 1. upsert_bin / read_bins round-trip
# ---------------------------------------------------------------------------


async def test_upsert_bin_round_trip() -> None:
    repo = InMemoryShiftPredictorRepo()
    rec = _bin(_FP, gear=3, rpm_bin=6500)
    await repo.upsert_bin(rec)

    result = await repo.read_bins(_FP)
    assert len(result) == 1
    assert result[0] == rec


# ---------------------------------------------------------------------------
# 2. Repeated upsert with same key updates in place
# ---------------------------------------------------------------------------


async def test_upsert_bin_updates_in_place() -> None:
    repo = InMemoryShiftPredictorRepo()
    await repo.upsert_bin(_bin(_FP, gear=3, rpm_bin=6500, count=1, q90=290.0))
    await repo.upsert_bin(_bin(_FP, gear=3, rpm_bin=6500, count=2, q90=310.0))

    result = await repo.read_bins(_FP)
    assert len(result) == 1
    assert result[0].count == 2
    assert result[0].q90_torque_nm == 310.0


# ---------------------------------------------------------------------------
# 3. upsert_bins batch with 3 distinct keys
# ---------------------------------------------------------------------------


async def test_upsert_bins_batch() -> None:
    repo = InMemoryShiftPredictorRepo()
    recs = [
        _bin(_FP, gear=1, rpm_bin=3000),
        _bin(_FP, gear=2, rpm_bin=4500),
        _bin(_FP, gear=3, rpm_bin=6000),
    ]
    await repo.upsert_bins(recs)

    result = await repo.read_bins(_FP)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# 4. read_bins returns [] for unknown fingerprint
# ---------------------------------------------------------------------------


async def test_read_bins_empty_for_unknown_fp() -> None:
    repo = InMemoryShiftPredictorRepo()
    result = await repo.read_bins(_FP)
    assert result == []


# ---------------------------------------------------------------------------
# 5. upsert_ratio / read_ratios round-trip + in-place update
# ---------------------------------------------------------------------------


async def test_upsert_ratio_round_trip() -> None:
    repo = InMemoryShiftPredictorRepo()
    rec = _ratio(_FP, gear=3)
    await repo.upsert_ratio(rec)

    result = await repo.read_ratios(_FP)
    assert len(result) == 1
    assert result[0] == rec


async def test_upsert_ratio_updates_in_place() -> None:
    repo = InMemoryShiftPredictorRepo()
    await repo.upsert_ratio(_ratio(_FP, gear=3, ratio=3.5))
    await repo.upsert_ratio(_ratio(_FP, gear=3, ratio=3.8))

    result = await repo.read_ratios(_FP)
    assert len(result) == 1
    assert result[0].ratio == 3.8


# ---------------------------------------------------------------------------
# 6. upsert_class_prior_bin / read_class_prior round-trip
# ---------------------------------------------------------------------------


async def test_upsert_class_prior_round_trip() -> None:
    repo = InMemoryShiftPredictorRepo()
    key = EngineClassKey(car_class="A", car_group=18, drivetrain_type="AWD", num_cylinders=6)
    rec = _class_prior(key, gear=3, rpm_bin=5500)
    await repo.upsert_class_prior_bin(rec)

    result = await repo.read_class_prior(key)
    assert len(result) == 1
    assert result[0] == rec


# ---------------------------------------------------------------------------
# 7. record_shift_event assigns id when None
# ---------------------------------------------------------------------------


async def test_record_shift_event_assigns_id() -> None:
    repo = InMemoryShiftPredictorRepo()
    sid = SessionId("sess-001")
    row = _shift_event(sid, _FP)
    assert row.id is None

    await repo.record_shift_event(row)
    stored = await repo.read_shift_events(sid)
    assert len(stored) == 1
    assert stored[0].id is not None


# ---------------------------------------------------------------------------
# 8. read_shift_events returns rows sorted ascending by shift_at
# ---------------------------------------------------------------------------


async def test_read_shift_events_sorted_ascending() -> None:
    repo = InMemoryShiftPredictorRepo()
    sid = SessionId("sess-002")
    later = datetime(2026, 5, 23, 10, 1, 0, tzinfo=UTC)
    earlier = datetime(2026, 5, 23, 10, 0, 0, tzinfo=UTC)

    # Insert later one first deliberately.
    await repo.record_shift_event(_shift_event(sid, _FP, shift_at=later))
    await repo.record_shift_event(_shift_event(sid, _FP, shift_at=earlier))

    result = await repo.read_shift_events(sid)
    assert len(result) == 2
    assert result[0].shift_at == earlier
    assert result[1].shift_at == later


# ---------------------------------------------------------------------------
# 9. reset_fingerprint deletes matching rows and returns counts
# ---------------------------------------------------------------------------


async def test_reset_fingerprint_deletes_and_returns_counts() -> None:
    repo = InMemoryShiftPredictorRepo()
    sid = SessionId("sess-003")

    # Populate _FP data.
    await repo.upsert_bin(_bin(_FP, gear=1, rpm_bin=3000))
    await repo.upsert_bin(_bin(_FP, gear=2, rpm_bin=4000))
    await repo.upsert_ratio(_ratio(_FP, gear=1))
    await repo.upsert_ratio(_ratio(_FP, gear=2))
    await repo.record_shift_event(_shift_event(sid, _FP))

    # Populate _FP2 data — must survive reset of _FP.
    await repo.upsert_bin(_bin(_FP2, gear=1, rpm_bin=3000))
    await repo.upsert_ratio(_ratio(_FP2, gear=1))

    # Populate a class prior — must also survive (not affected by reset).
    key = EngineClassKey(car_class="A", car_group=18, drivetrain_type="AWD", num_cylinders=6)
    await repo.upsert_class_prior_bin(_class_prior(key, gear=1, rpm_bin=3000))

    counts = await repo.reset_fingerprint(_FP)

    assert counts.engine_curves == 2
    assert counts.gear_ratios == 2
    assert counts.shift_events == 1

    # _FP rows gone.
    assert await repo.read_bins(_FP) == []
    assert await repo.read_ratios(_FP) == []
    assert await repo.read_shift_events(sid) == []

    # _FP2 rows untouched.
    assert len(await repo.read_bins(_FP2)) == 1
    assert len(await repo.read_ratios(_FP2)) == 1

    # Class prior untouched.
    assert len(await repo.read_class_prior(key)) == 1
