"""Unit tests for BinTrainer — Welford + P² quantile + EWMA decay.

Tests cover correctness of running statistics, bin isolation, snapshot/hydrate
round-trips, flush persistence, sample counting, and last_updated tracking.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from fh6.application.services.shift.bin_trainer import BinTrainer
from fh6.domain.ports.shift_predictor_repo import BinRecord
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_FP_A = EngineFingerprint(car_ordinal=2451, performance_index=812, num_cylinders=6)
_FP_B = EngineFingerprint(car_ordinal=9999, performance_index=700, num_cylinders=4)

_NOW = datetime(2026, 5, 23, 10, 0, 0, tzinfo=UTC)
_LATER = datetime(2026, 5, 23, 11, 0, 0, tzinfo=UTC)


def _feed(
    trainer: BinTrainer,
    fp: EngineFingerprint,
    gear: int,
    rpm: float,
    torques: list[float],
    boost: float = 5.0,
    at: datetime = _NOW,
) -> None:
    """Feed a list of torque values into the trainer for the given bin."""
    for t in torques:
        trainer.update(fp, gear, rpm, t, boost, at)


# ---------------------------------------------------------------------------
# 1. Welford correctness
# ---------------------------------------------------------------------------


def test_welford_mean_and_variance() -> None:
    """Feed 1000 gauss(400, 20) samples → mean ≈ 400 (±5), variance ≈ 400 (±50)."""
    rng = random.Random(42)
    samples = [rng.gauss(400, 20) for _ in range(1000)]

    trainer = BinTrainer(half_life_samples=10_000)  # effectively no decay
    _feed(trainer, _FP_A, gear=3, rpm=6500.0, torques=samples)

    snap = trainer.snapshot(_FP_A)
    rec = snap[(3, 65)]  # rpm_bin = floor(6500/100) = 65

    assert rec.mean_torque_nm == pytest.approx(400.0, abs=5.0)
    # variance = M2 / count; since EWMA is applied but half_life is huge,
    # effective count is ~1000 and variance should be near sigma^2 = 400
    variance = rec.m2_torque / rec.count
    assert variance == pytest.approx(400.0, abs=50.0)


# ---------------------------------------------------------------------------
# 2. P² q90 correctness
# ---------------------------------------------------------------------------


def test_p2_q90_correctness() -> None:
    """Feed 1000 gauss(400, 20) samples → q90 ≈ 425.6 (within ±6)."""
    rng = random.Random(42)
    samples = [rng.gauss(400, 20) for _ in range(1000)]

    trainer = BinTrainer(half_life_samples=10_000)
    _feed(trainer, _FP_A, gear=3, rpm=6500.0, torques=samples)

    snap = trainer.snapshot(_FP_A)
    rec = snap[(3, 65)]

    # 90th percentile of N(400, 20): 400 + 1.2816 * 20 ≈ 425.6
    assert rec.q90_torque_nm == pytest.approx(425.6, abs=6.0)


# ---------------------------------------------------------------------------
# 3. EWMA migration: old data fades
# ---------------------------------------------------------------------------


def test_ewma_mean_migrates_toward_recent_data() -> None:
    """Mean should be between 500 and 600 after EWMA with half_life=500."""
    trainer = BinTrainer(half_life_samples=500)

    # Phase 1: 1000 samples at torque=400
    phase1 = [400.0] * 1000
    _feed(trainer, _FP_A, gear=3, rpm=6500.0, torques=phase1, at=_NOW)

    # Phase 2: 1000 samples at torque=600
    phase2 = [600.0] * 1000
    _feed(trainer, _FP_A, gear=3, rpm=6500.0, torques=phase2, at=_LATER)

    snap = trainer.snapshot(_FP_A)
    rec = snap[(3, 65)]

    # EWMA with half_life=500 means old data fades; recent 600 dominates
    assert rec.mean_torque_nm > 500.0
    assert rec.mean_torque_nm < 600.0


# ---------------------------------------------------------------------------
# 4. Bin isolation: no bleed between (gear, rpm_bin) or fingerprint
# ---------------------------------------------------------------------------


def test_bin_isolation_no_bleed() -> None:
    """Updates to one bin must not affect adjacent bins or other fingerprints."""
    trainer = BinTrainer(half_life_samples=10_000)

    # Update only (FP_A, gear=3, rpm_bin=65)
    _feed(trainer, _FP_A, gear=3, rpm=6500.0, torques=[400.0] * 50)

    snap_a = trainer.snapshot(_FP_A)
    snap_b = trainer.snapshot(_FP_B)

    # Adjacent rpm_bin=66 (rpm=6600) should be absent
    assert (3, 66) not in snap_a

    # Other fingerprint should have no bins at all
    assert snap_b == {}

    # Adjacent gear (gear=4, same rpm_bin) should be absent
    assert (4, 65) not in snap_a


# ---------------------------------------------------------------------------
# 5. snapshot() shape and correctness
# ---------------------------------------------------------------------------


def test_snapshot_shape_and_fingerprint() -> None:
    """Snapshot is a dict keyed by (gear, rpm_bin); BinRecord.fingerprint matches."""
    trainer = BinTrainer(half_life_samples=10_000)
    _feed(trainer, _FP_A, gear=3, rpm=6500.0, torques=[300.0, 350.0, 400.0])

    snap = trainer.snapshot(_FP_A)

    assert isinstance(snap, dict)
    assert len(snap) == 1

    key, rec = next(iter(snap.items()))
    assert key == (3, 65)
    assert isinstance(rec, BinRecord)
    assert rec.fingerprint == _FP_A
    assert rec.gear == 3
    assert rec.rpm_bin == 65


# ---------------------------------------------------------------------------
# 6. hydrate() round-trip
# ---------------------------------------------------------------------------


def test_hydrate_round_trip() -> None:
    """Hydrating synthetic BinRecords should be reflected in snapshot."""
    trainer = BinTrainer(half_life_samples=10_000)

    synthetic_records = [
        BinRecord(
            fingerprint=_FP_A,
            gear=2,
            rpm_bin=55,
            count=100,
            mean_torque_nm=350.0,
            m2_torque=2000.0,
            q90_torque_nm=380.0,
            mean_boost_psi=7.5,
            last_updated=_NOW,
        ),
        BinRecord(
            fingerprint=_FP_A,
            gear=3,
            rpm_bin=65,
            count=200,
            mean_torque_nm=400.0,
            m2_torque=3500.0,
            q90_torque_nm=425.0,
            mean_boost_psi=8.0,
            last_updated=_NOW,
        ),
    ]

    trainer.hydrate(_FP_A, synthetic_records)
    snap = trainer.snapshot(_FP_A)

    assert len(snap) == 2
    assert (2, 55) in snap
    assert (3, 65) in snap

    rec_g2 = snap[(2, 55)]
    assert rec_g2.fingerprint == _FP_A
    assert rec_g2.count == pytest.approx(100.0, rel=1e-6)
    assert rec_g2.mean_torque_nm == pytest.approx(350.0, rel=1e-6)
    assert rec_g2.q90_torque_nm == pytest.approx(380.0, rel=1e-6)

    rec_g3 = snap[(3, 65)]
    assert rec_g3.count == pytest.approx(200.0, rel=1e-6)
    assert rec_g3.mean_torque_nm == pytest.approx(400.0, rel=1e-6)


# ---------------------------------------------------------------------------
# 7. flush() calls repo.upsert_bins once with all snapshot records
# ---------------------------------------------------------------------------


class _StubRepo:
    """Minimal stub that records calls to upsert_bins."""

    def __init__(self) -> None:
        self.calls: list[Sequence[BinRecord]] = []

    async def upsert_bins(self, recs: Sequence[BinRecord]) -> None:
        self.calls.append(list(recs))


async def test_flush_calls_upsert_bins_once() -> None:
    """flush() should call repo.upsert_bins exactly once with all bins."""
    trainer = BinTrainer(half_life_samples=10_000)
    _feed(trainer, _FP_A, gear=3, rpm=6500.0, torques=[400.0] * 10)
    _feed(trainer, _FP_A, gear=4, rpm=7000.0, torques=[350.0] * 10)
    _feed(trainer, _FP_B, gear=2, rpm=5500.0, torques=[300.0] * 10)

    repo = _StubRepo()
    await trainer.flush(repo)

    assert len(repo.calls) == 1
    # All 3 bins should be flushed
    flushed = repo.calls[0]
    assert len(flushed) == 3

    # All flushed records are BinRecord instances
    for rec in flushed:
        assert isinstance(rec, BinRecord)


async def test_flush_preserves_in_memory_state() -> None:
    """After flush, in-memory state is still intact for continued updates."""
    trainer = BinTrainer(half_life_samples=10_000)
    _feed(trainer, _FP_A, gear=3, rpm=6500.0, torques=[400.0] * 20)

    repo = _StubRepo()
    await trainer.flush(repo)

    # State should still be accessible
    snap = trainer.snapshot(_FP_A)
    assert (3, 65) in snap
    assert snap[(3, 65)].count == pytest.approx(20.0, rel=0.1)


# ---------------------------------------------------------------------------
# 8. sample_count(fp, gear)
# ---------------------------------------------------------------------------


def test_sample_count_sums_across_rpm_bins() -> None:
    """sample_count should sum count across all rpm bins for that fp+gear."""
    trainer = BinTrainer(half_life_samples=10_000)
    # gear=3, two distinct rpm bins: 6500 (bin=65) and 6600 (bin=66)
    _feed(trainer, _FP_A, gear=3, rpm=6500.0, torques=[400.0] * 30)
    _feed(trainer, _FP_A, gear=3, rpm=6600.0, torques=[410.0] * 20)
    # gear=4, different gear
    _feed(trainer, _FP_A, gear=4, rpm=7000.0, torques=[380.0] * 10)

    count_g3 = trainer.sample_count(_FP_A, gear=3)
    # Due to EWMA with huge half-life, count ~= 30 + 20 = 50
    assert count_g3 == pytest.approx(50.0, rel=0.1)

    count_g4 = trainer.sample_count(_FP_A, gear=4)
    assert count_g4 == pytest.approx(10.0, rel=0.1)


def test_sample_count_empty_returns_zero() -> None:
    """sample_count on an unknown fingerprint or gear returns 0."""
    trainer = BinTrainer(half_life_samples=10_000)
    assert trainer.sample_count(_FP_A, gear=3) == 0
    assert trainer.sample_count(_FP_B, gear=1) == 0

    # Feed some data to FP_A gear=3, then check FP_B gear=3 still returns 0
    _feed(trainer, _FP_A, gear=3, rpm=6500.0, torques=[400.0] * 10)
    assert trainer.sample_count(_FP_B, gear=3) == 0


# ---------------------------------------------------------------------------
# 9. Boost mean tracks updates
# ---------------------------------------------------------------------------


def test_boost_mean_tracks_updates() -> None:
    """mean_boost_psi should reflect the running average of boost_psi values."""
    trainer = BinTrainer(half_life_samples=10_000)

    # Feed 10 samples with boost=10.0, then 10 with boost=20.0
    for _ in range(10):
        trainer.update(_FP_A, 3, 6500.0, 400.0, 10.0, _NOW)
    for _ in range(10):
        trainer.update(_FP_A, 3, 6500.0, 400.0, 20.0, _NOW)

    snap = trainer.snapshot(_FP_A)
    rec = snap[(3, 65)]

    # Running mean of boost: 10 * 10 + 10 * 20 / 20 = 15.0, but EWMA gives
    # more weight to recent; with huge half-life expect value between 10 and 20
    assert rec.mean_boost_psi > 10.0
    assert rec.mean_boost_psi < 20.0


def test_boost_mean_constant_value() -> None:
    """When all boost values are the same, mean_boost_psi equals that value."""
    trainer = BinTrainer(half_life_samples=10_000)

    for _ in range(50):
        trainer.update(_FP_A, 3, 6500.0, 400.0, 8.5, _NOW)

    snap = trainer.snapshot(_FP_A)
    rec = snap[(3, 65)]

    assert rec.mean_boost_psi == pytest.approx(8.5, abs=0.01)


# ---------------------------------------------------------------------------
# 10. last_updated is the most recent `at` timestamp
# ---------------------------------------------------------------------------


def test_last_updated_tracks_most_recent_timestamp() -> None:
    """last_updated should equal the most recent `at` passed to update."""
    trainer = BinTrainer(half_life_samples=10_000)

    t1 = datetime(2026, 5, 23, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 5, 23, 11, 0, 0, tzinfo=UTC)
    t3 = datetime(2026, 5, 23, 12, 0, 0, tzinfo=UTC)

    trainer.update(_FP_A, 3, 6500.0, 400.0, 5.0, t1)
    snap1 = trainer.snapshot(_FP_A)
    assert snap1[(3, 65)].last_updated == t1

    trainer.update(_FP_A, 3, 6500.0, 410.0, 5.0, t3)
    trainer.update(_FP_A, 3, 6500.0, 420.0, 5.0, t2)  # out-of-order but t3 already seen

    snap2 = trainer.snapshot(_FP_A)
    # last_updated should be max of all timestamps seen
    assert snap2[(3, 65)].last_updated == t3
