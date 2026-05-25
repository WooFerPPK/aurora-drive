"""Unit tests for ClassPriorBuilder.maybe_rebuild aggregation (Task 5 / FR-035).

Covers the v2 rebuild path: weighted aggregation across qualifying
fingerprints, cooldown blocking back-to-back rebuilds, and exclusion of
paused fingerprints.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fh6.application.services.shift.class_prior import ClassPriorBuilder
from fh6.domain.ports.shift_predictor_repo import BinRecord
from fh6.domain.value_objects.engine_fingerprint import (
    EngineClassKey,
    EngineFingerprint,
)
from tests.contract.fake_repos import InMemoryShiftPredictorRepo

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo() -> InMemoryShiftPredictorRepo:
    """Fresh in-memory repo for each test."""
    return InMemoryShiftPredictorRepo()


@pytest.fixture
def builder(repo: InMemoryShiftPredictorRepo) -> ClassPriorBuilder:
    """Fresh ClassPriorBuilder for each test."""
    return ClassPriorBuilder(repo=repo)


@pytest.fixture
def class_key() -> EngineClassKey:
    """Sample EngineClassKey for testing."""
    return EngineClassKey(
        car_class="S",
        car_group=1,
        drivetrain_type="AWD",
        num_cylinders=8,
    )


@pytest.fixture
def fp_a() -> EngineFingerprint:
    return EngineFingerprint(car_ordinal=1001, performance_index=800, num_cylinders=8)


@pytest.fixture
def fp_b() -> EngineFingerprint:
    return EngineFingerprint(car_ordinal=1002, performance_index=800, num_cylinders=8)


@pytest.fixture
def fp_c() -> EngineFingerprint:
    return EngineFingerprint(car_ordinal=1003, performance_index=800, num_cylinders=8)


async def _seed_bins(
    repo: InMemoryShiftPredictorRepo,
    fp: EngineFingerprint,
    *,
    count: int,
    q90: float,
    gear: int = 3,
    n_bins: int = 6,
) -> None:
    """Seed `n_bins` BinRecords for `fp` at the given gear (rpm_bins 30..30+n_bins-1)."""
    now = datetime.now(tz=UTC)
    for i in range(n_bins):
        rpm_bin = 30 + i
        await repo.upsert_bin(
            BinRecord(
                fingerprint=fp,
                gear=gear,
                rpm_bin=rpm_bin,
                count=count,
                mean_torque_nm=q90 * 0.8,
                m2_torque=0.0,
                q90_torque_nm=q90,
                mean_boost_psi=0.0,
                last_updated=now,
            )
        )


# ---------------------------------------------------------------------------
# Test 1: weighted aggregation across two qualifying fingerprints
# ---------------------------------------------------------------------------


async def test_maybe_rebuild_aggregates_weighted_mean_and_excludes_below_threshold(
    builder: ClassPriorBuilder,
    repo: InMemoryShiftPredictorRepo,
    class_key: EngineClassKey,
    fp_a: EngineFingerprint,
    fp_b: EngineFingerprint,
    fp_c: EngineFingerprint,
) -> None:
    """A and B qualify (>=1000 samples) and aggregate; C (600) is excluded."""
    # Fingerprint A: 6 bins, count=300, q90=400 -> total 1800
    await _seed_bins(repo, fp_a, count=300, q90=400.0)
    # Fingerprint B: 6 bins, count=200, q90=500 -> total 1200
    await _seed_bins(repo, fp_b, count=200, q90=500.0)
    # Fingerprint C: 6 bins, count=100, q90=600 -> total 600 (below threshold)
    await _seed_bins(repo, fp_c, count=100, q90=600.0)

    await builder.maybe_rebuild(
        class_key,
        fp_a,
        candidate_fingerprints=[fp_a, fp_b, fp_c],
        cooldown_s=300,
        min_total_samples=1_000,
    )

    rows = await repo.read_class_prior(class_key)
    assert len(rows) == 6, f"expected 6 aggregated rows, got {len(rows)}"

    # Weighted mean: (300*400 + 200*500) / 500 = 440.0
    # Total count: 500
    for row in rows:
        assert row.gear == 3
        assert row.count == 500, f"unexpected count {row.count}"
        assert row.q90_torque_nm == pytest.approx(440.0), f"unexpected q90 {row.q90_torque_nm}"
        assert row.class_key == class_key


# ---------------------------------------------------------------------------
# Test 2: cooldown blocks back-to-back rebuilds
# ---------------------------------------------------------------------------


async def test_maybe_rebuild_cooldown_blocks_second_call(
    builder: ClassPriorBuilder,
    repo: InMemoryShiftPredictorRepo,
    class_key: EngineClassKey,
    fp_a: EngineFingerprint,
    fp_b: EngineFingerprint,
) -> None:
    """Two consecutive maybe_rebuild calls within cooldown -> second is a no-op."""
    await _seed_bins(repo, fp_a, count=300, q90=400.0)
    await _seed_bins(repo, fp_b, count=200, q90=500.0)

    # First call: should rebuild and produce 6 rows.
    await builder.maybe_rebuild(
        class_key,
        fp_a,
        candidate_fingerprints=[fp_a, fp_b],
        cooldown_s=300,
        min_total_samples=1_000,
    )
    rows_after_first = await repo.read_class_prior(class_key)
    assert len(rows_after_first) == 6
    first_built_at = rows_after_first[0].last_built

    # Mutate the repo so any second rebuild would produce a *different* q90,
    # which would be visible in last_built/q90 values.
    # We simulate the cooldown holding: even if we add more samples, the
    # repo should not see any new upsert_class_prior_bin calls.
    # We detect this by snapshotting the rows; identical rows post-second-call
    # means no upsert ran.
    await _seed_bins(repo, fp_b, count=999_999, q90=999.0)

    await builder.maybe_rebuild(
        class_key,
        fp_a,
        candidate_fingerprints=[fp_a, fp_b],
        cooldown_s=300,
        min_total_samples=1_000,
    )
    rows_after_second = await repo.read_class_prior(class_key)
    assert len(rows_after_second) == 6
    # Values must be identical (no upsert happened during the second call).
    for row in rows_after_second:
        assert row.last_built == first_built_at, "cooldown should have blocked the second rebuild"
        assert row.q90_torque_nm == pytest.approx(440.0), (
            "q90 should be unchanged from the first rebuild"
        )
        assert row.count == 500


# ---------------------------------------------------------------------------
# Test 3: excluded_paused removes fingerprints from the candidate pool
# ---------------------------------------------------------------------------


async def test_maybe_rebuild_excludes_paused_fingerprints(
    builder: ClassPriorBuilder,
    repo: InMemoryShiftPredictorRepo,
    class_key: EngineClassKey,
    fp_a: EngineFingerprint,
    fp_b: EngineFingerprint,
) -> None:
    """excluded_paused={A} drops A; B alone (1200 samples) still qualifies."""
    await _seed_bins(repo, fp_a, count=300, q90=400.0)
    await _seed_bins(repo, fp_b, count=200, q90=500.0)

    await builder.maybe_rebuild(
        class_key,
        fp_b,
        candidate_fingerprints=[fp_a, fp_b],
        excluded_paused={fp_a},
        cooldown_s=300,
        min_total_samples=1_000,
    )

    rows = await repo.read_class_prior(class_key)
    assert len(rows) == 6
    # Only B contributes -> q90 = 500.0, count = 200 per bin.
    for row in rows:
        assert row.q90_torque_nm == pytest.approx(500.0)
        assert row.count == 200
