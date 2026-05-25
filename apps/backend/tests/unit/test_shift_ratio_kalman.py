"""Unit tests for RatioKalman per-gear scalar Kalman filter (FR-006, FR-007)."""

from __future__ import annotations

import random
from datetime import UTC, datetime

import pytest

from fh6.application.services.shift.ratio_kalman import RatioKalman, RatioReading
from fh6.domain.ports.shift_predictor_repo import RatioRecord
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FP = EngineFingerprint(car_ordinal=2451, performance_index=812, num_cylinders=6)
_FP2 = EngineFingerprint(car_ordinal=9999, performance_index=700, num_cylinders=4)
_NOW = datetime(2026, 5, 23, 10, 0, 0, tzinfo=UTC)


def _make_ratio_record(
    fp: EngineFingerprint,
    gear: int,
    *,
    ratio: float = 200.0,
    variance: float = 0.05,
) -> RatioRecord:
    return RatioRecord(
        fingerprint=fp,
        gear=gear,
        ratio=ratio,
        variance=variance,
        last_updated=_NOW,
    )


# ---------------------------------------------------------------------------
# 1. Convergence test
# ---------------------------------------------------------------------------


class TestConvergence:
    """Feed 100 noiseless measurements → locked within ~80 updates."""

    def test_locks_on_noiseless_signal(self):
        kf = RatioKalman()
        for _ in range(100):
            kf.update(_FP, 4, 200.0)

        result = kf.read(_FP, 4)
        assert result is not None
        assert isinstance(result, RatioReading)
        assert result.ratio == pytest.approx(200.0, abs=0.01)
        assert result.variance < 0.1  # lock_var_threshold default
        assert result.locked is True


# ---------------------------------------------------------------------------
# 2. Noise rejection
# ---------------------------------------------------------------------------


class TestNoiseRejection:
    """Feed 100 measurements with Gaussian noise (σ=5) → mean stays within ±2."""

    def test_noise_rejected(self):
        rng = random.Random(42)
        kf = RatioKalman()
        for _ in range(100):
            noisy = 200.0 + rng.gauss(0, 5)
            kf.update(_FP, 4, noisy)

        result = kf.read(_FP, 4)
        assert result is not None
        assert abs(result.ratio - 200.0) < 2.0


# ---------------------------------------------------------------------------
# 3. Gears are independent
# ---------------------------------------------------------------------------


class TestGearsIndependent:
    """Updating gear 4 must not affect gear 3."""

    def test_gear3_untouched(self):
        kf = RatioKalman()
        for _ in range(50):
            kf.update(_FP, 4, 200.0)

        assert kf.read(_FP, 3) is None

    def test_gear3_independent_from_gear4(self):
        kf = RatioKalman()
        for _ in range(50):
            kf.update(_FP, 4, 200.0)
        kf.update(_FP, 3, 300.0)

        result4 = kf.read(_FP, 4)
        result3 = kf.read(_FP, 3)

        assert result4 is not None
        assert result3 is not None
        # gear 3 estimate anchored near 300.0
        assert result3.ratio == pytest.approx(300.0, abs=1.0)
        # gear 4 estimate not shifted toward 300.0
        assert result4.ratio == pytest.approx(200.0, abs=0.1)


# ---------------------------------------------------------------------------
# 4. Re-lock after sudden ratio change
# ---------------------------------------------------------------------------


class TestRelockAfterChange:
    """After locking on 200, then 50 measurements at 120, ratio must track 120."""

    def test_relock_after_sudden_change(self):
        kf = RatioKalman()
        # First lock onto 200
        for _ in range(100):
            kf.update(_FP, 4, 200.0)

        # Confirm locked
        pre = kf.read(_FP, 4)
        assert pre is not None
        assert pre.locked is True

        # Now shift to 120 — after 50 updates the filter should track new ratio
        for _ in range(50):
            kf.update(_FP, 4, 120.0)

        post = kf.read(_FP, 4)
        assert post is not None
        assert abs(post.ratio - 120.0) < 5.0


# ---------------------------------------------------------------------------
# 5. read returns None for unobserved gear
# ---------------------------------------------------------------------------


class TestReadNoneUnobserved:
    def test_none_for_completely_new_fp(self):
        kf = RatioKalman()
        assert kf.read(_FP, 4) is None

    def test_none_for_unobserved_gear_on_known_fp(self):
        kf = RatioKalman()
        kf.update(_FP, 4, 200.0)
        assert kf.read(_FP, 3) is None

    def test_none_for_different_fp(self):
        kf = RatioKalman()
        kf.update(_FP, 4, 200.0)
        assert kf.read(_FP2, 4) is None


# ---------------------------------------------------------------------------
# 6. snapshot returns one RatioRecord per observed gear
# ---------------------------------------------------------------------------


class TestSnapshot:
    def test_snapshot_empty_when_no_updates(self):
        kf = RatioKalman()
        snap = kf.snapshot(_FP)
        assert snap == {}

    def test_snapshot_one_record_per_gear(self):
        kf = RatioKalman()
        kf.update(_FP, 3, 300.0)
        kf.update(_FP, 4, 200.0)
        kf.update(_FP, 5, 150.0)

        snap = kf.snapshot(_FP)
        assert len(snap) == 3
        assert set(snap.keys()) == {3, 4, 5}

    def test_snapshot_records_have_correct_fingerprint(self):
        kf = RatioKalman()
        kf.update(_FP, 4, 200.0)

        snap = kf.snapshot(_FP)
        for gear, rec in snap.items():
            assert isinstance(rec, RatioRecord)
            assert rec.fingerprint == _FP
            assert rec.gear == gear

    def test_snapshot_does_not_include_other_fp(self):
        kf = RatioKalman()
        kf.update(_FP, 4, 200.0)
        kf.update(_FP2, 4, 150.0)

        snap_fp = kf.snapshot(_FP)
        snap_fp2 = kf.snapshot(_FP2)

        assert len(snap_fp) == 1
        assert len(snap_fp2) == 1
        assert snap_fp[4].fingerprint == _FP
        assert snap_fp2[4].fingerprint == _FP2


# ---------------------------------------------------------------------------
# 7. hydrate round-trip
# ---------------------------------------------------------------------------


class TestHydrate:
    def test_hydrate_then_snapshot_preserves_ratio_variance(self):
        records = [
            _make_ratio_record(_FP, 3, ratio=300.0, variance=0.02),
            _make_ratio_record(_FP, 4, ratio=200.0, variance=0.05),
        ]

        kf = RatioKalman()
        kf.hydrate(_FP, records)

        snap = kf.snapshot(_FP)
        assert len(snap) == 2

        rec3 = snap[3]
        assert rec3.ratio == pytest.approx(300.0, abs=1e-9)
        assert rec3.variance == pytest.approx(0.02, abs=1e-9)

        rec4 = snap[4]
        assert rec4.ratio == pytest.approx(200.0, abs=1e-9)
        assert rec4.variance == pytest.approx(0.05, abs=1e-9)

    def test_hydrate_replaces_existing_state(self):
        kf = RatioKalman()
        kf.update(_FP, 4, 200.0)

        new_records = [_make_ratio_record(_FP, 4, ratio=150.0, variance=0.03)]
        kf.hydrate(_FP, new_records)

        snap = kf.snapshot(_FP)
        assert len(snap) == 1
        assert snap[4].ratio == pytest.approx(150.0, abs=1e-9)

    def test_hydrate_allows_read_after_restore(self):
        records = [_make_ratio_record(_FP, 4, ratio=200.0, variance=0.05)]
        kf = RatioKalman()
        kf.hydrate(_FP, records)

        result = kf.read(_FP, 4)
        assert result is not None
        assert result.ratio == pytest.approx(200.0, abs=1e-9)
        assert result.variance == pytest.approx(0.05, abs=1e-9)


# ---------------------------------------------------------------------------
# 8. flush calls upsert_ratio once per (fp, gear)
# ---------------------------------------------------------------------------


class StubRepo:
    """Minimal stub that records upsert_ratio calls."""

    def __init__(self) -> None:
        self.upsert_calls: list[RatioRecord] = []

    async def upsert_ratio(self, rec: RatioRecord) -> None:
        self.upsert_calls.append(rec)

    # Satisfy Protocol for other methods (not used in these tests)
    async def upsert_bin(self, rec: object) -> None: ...
    async def upsert_bins(self, recs: object) -> None: ...
    async def read_bins(self, fp: object) -> list:
        return []

    async def read_ratios(self, fp: object) -> list:
        return []

    async def upsert_class_prior_bin(self, rec: object) -> None: ...
    async def read_class_prior(self, key: object) -> list:
        return []

    async def record_shift_event(self, row: object) -> None: ...
    async def read_shift_events(self, session_id: object) -> list:
        return []

    async def reset_fingerprint(self, fp: object) -> object: ...


class TestFlush:
    async def test_flush_calls_upsert_ratio_per_gear(self):
        kf = RatioKalman()
        kf.update(_FP, 3, 300.0)
        kf.update(_FP, 4, 200.0)
        kf.update(_FP, 5, 150.0)
        kf.update(_FP2, 4, 180.0)

        repo = StubRepo()
        await kf.flush(repo)

        assert len(repo.upsert_calls) == 4
        fps_gears = {(r.fingerprint, r.gear) for r in repo.upsert_calls}
        assert fps_gears == {(_FP, 3), (_FP, 4), (_FP, 5), (_FP2, 4)}

    async def test_flush_empty_makes_no_calls(self):
        kf = RatioKalman()
        repo = StubRepo()
        await kf.flush(repo)
        assert repo.upsert_calls == []


# ---------------------------------------------------------------------------
# 9. Lock threshold respected
# ---------------------------------------------------------------------------


class TestLockThreshold:
    """With very high measurement_noise and few samples, locked should be False."""

    def test_high_noise_stays_unlocked(self):
        # Very high measurement noise → variance converges slowly
        kf = RatioKalman(measurement_noise=1_000_000.0)
        for _ in range(10):
            kf.update(_FP, 4, 200.0)

        result = kf.read(_FP, 4)
        assert result is not None
        assert result.locked is False

    def test_locked_requires_stability_window(self):
        """Even with tight variance, must have enough observations for stability window."""
        kf = RatioKalman(stability_window=50)
        # Only 10 updates — not enough to fill stability ring buffer
        for _ in range(10):
            kf.update(_FP, 4, 200.0)

        result = kf.read(_FP, 4)
        assert result is not None
        # May or may not have low variance, but locked should be False due to window
        # (variance after 10 noiseless updates may still be below threshold, but window not full)
        assert result.locked is False
