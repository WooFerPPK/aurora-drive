"""Unit tests for ClassPriorBuilder (Task 10).

Tests the lazy caching behavior and rebuild marking for the class-level
prior bin aggregator.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fh6.application.services.shift.class_prior import ClassPriorBuilder
from fh6.domain.ports.shift_predictor_repo import ClassPriorBin
from fh6.domain.value_objects.engine_fingerprint import (
    EngineClassKey,
    EngineFingerprint,
)
from tests.contract.fake_repos import InMemoryShiftPredictorRepo


@pytest.fixture
def repo() -> InMemoryShiftPredictorRepo:
    """Fresh in-memory repo for each test."""
    return InMemoryShiftPredictorRepo()


@pytest.fixture
def builder(repo: InMemoryShiftPredictorRepo) -> ClassPriorBuilder:
    """Fresh ClassPriorBuilder for each test."""
    return ClassPriorBuilder(repo=repo)


@pytest.fixture
def sample_key() -> EngineClassKey:
    """Sample EngineClassKey for testing."""
    return EngineClassKey(
        car_class="S",
        car_group=1,
        drivetrain_type="AWD",
        num_cylinders=8,
    )


@pytest.fixture
def sample_fp() -> EngineFingerprint:
    """Sample EngineFingerprint for testing."""
    return EngineFingerprint(
        car_ordinal=123,
        performance_index=456,
        num_cylinders=8,
    )


@pytest.fixture
def sample_bins(sample_key: EngineClassKey) -> list[ClassPriorBin]:
    """Three sample ClassPriorBins for the test key."""
    now = datetime.now(tz=UTC)
    return [
        ClassPriorBin(
            class_key=sample_key,
            gear=3,
            rpm_bin=40,
            count=10,
            q90_torque_nm=250.0,
            last_built=now,
        ),
        ClassPriorBin(
            class_key=sample_key,
            gear=3,
            rpm_bin=50,
            count=15,
            q90_torque_nm=260.0,
            last_built=now,
        ),
        ClassPriorBin(
            class_key=sample_key,
            gear=4,
            rpm_bin=35,
            count=12,
            q90_torque_nm=240.0,
            last_built=now,
        ),
    ]


# --- Test 1: read hits repo on first call ---


@pytest.mark.asyncio
async def test_read_hits_repo_on_first_call(
    builder: ClassPriorBuilder,
    repo: InMemoryShiftPredictorRepo,
    sample_key: EngineClassKey,
) -> None:
    """Empty cache + repo with no rows for the key -> returns [] and caches."""
    # Start with empty repo.
    result = await builder.read(sample_key)

    assert result == []
    assert sample_key in builder._cache


# --- Test 2: read returns cached on second call ---


@pytest.mark.asyncio
async def test_read_returns_cached_on_second_call(
    builder: ClassPriorBuilder,
    repo: InMemoryShiftPredictorRepo,
    sample_key: EngineClassKey,
    sample_bins: list[ClassPriorBin],
) -> None:
    """Pre-populate cache, modify repo, second read returns cached value."""
    # Seed repo with 3 bins
    for bin_rec in sample_bins:
        await repo.upsert_class_prior_bin(bin_rec)

    # First read: fetches from repo
    result1 = await builder.read(sample_key)
    assert len(result1) == 3

    # Add a 4th bin to the repo
    now = datetime.now(tz=UTC)
    fourth_bin = ClassPriorBin(
        class_key=sample_key,
        gear=5,
        rpm_bin=45,
        count=20,
        q90_torque_nm=270.0,
        last_built=now,
    )
    await repo.upsert_class_prior_bin(fourth_bin)

    # Second read: should still return 3 (cached, not re-fetched)
    result2 = await builder.read(sample_key)
    assert len(result2) == 3


# --- Test 3: maybe_rebuild makes next read re-fetch ---


@pytest.mark.asyncio
async def test_maybe_rebuild_makes_next_read_refetch(
    builder: ClassPriorBuilder,
    repo: InMemoryShiftPredictorRepo,
    sample_key: EngineClassKey,
    sample_fp: EngineFingerprint,
    sample_bins: list[ClassPriorBin],
) -> None:
    """Call maybe_rebuild -> next read re-fetches from repo."""
    # Seed repo with 3 bins
    for bin_rec in sample_bins:
        await repo.upsert_class_prior_bin(bin_rec)

    # First read: fetches from repo
    result1 = await builder.read(sample_key)
    assert len(result1) == 3

    # Add a 4th bin to the repo
    now = datetime.now(tz=UTC)
    fourth_bin = ClassPriorBin(
        class_key=sample_key,
        gear=5,
        rpm_bin=45,
        count=20,
        q90_torque_nm=270.0,
        last_built=now,
    )
    await repo.upsert_class_prior_bin(fourth_bin)

    # Call maybe_rebuild to mark dirty
    await builder.maybe_rebuild(sample_key, sample_fp)

    # Next read: should re-fetch and return 4
    result2 = await builder.read(sample_key)
    assert len(result2) == 4


# --- Test 4: invalidate drops cache ---


@pytest.mark.asyncio
async def test_invalidate_drops_cache(
    builder: ClassPriorBuilder,
    repo: InMemoryShiftPredictorRepo,
    sample_key: EngineClassKey,
    sample_bins: list[ClassPriorBin],
) -> None:
    """Call invalidate -> next read re-fetches from repo."""
    # Seed repo with 3 bins
    for bin_rec in sample_bins:
        await repo.upsert_class_prior_bin(bin_rec)

    # First read: fetches from repo
    result1 = await builder.read(sample_key)
    assert len(result1) == 3

    # Add a 4th bin to the repo
    now = datetime.now(tz=UTC)
    fourth_bin = ClassPriorBin(
        class_key=sample_key,
        gear=5,
        rpm_bin=45,
        count=20,
        q90_torque_nm=270.0,
        last_built=now,
    )
    await repo.upsert_class_prior_bin(fourth_bin)

    # Invalidate the cache
    builder.invalidate(sample_key)

    # Next read: should re-fetch and return 4
    result2 = await builder.read(sample_key)
    assert len(result2) == 4


# --- Test 5: different keys are independent ---


@pytest.mark.asyncio
async def test_different_keys_are_independent(
    builder: ClassPriorBuilder,
    repo: InMemoryShiftPredictorRepo,
) -> None:
    """Two distinct EngineClassKeys -> reading one doesn't affect the other."""
    key1 = EngineClassKey(car_class="S", car_group=1, drivetrain_type="AWD", num_cylinders=8)
    key2 = EngineClassKey(car_class="A", car_group=2, drivetrain_type="FWD", num_cylinders=6)

    now = datetime.now(tz=UTC)

    # Seed repo with bins for key1 only
    bin1 = ClassPriorBin(
        class_key=key1,
        gear=3,
        rpm_bin=40,
        count=10,
        q90_torque_nm=250.0,
        last_built=now,
    )
    await repo.upsert_class_prior_bin(bin1)

    # Read key1
    result1 = await builder.read(key1)
    assert len(result1) == 1

    # Read key2 (no bins in repo)
    result2 = await builder.read(key2)
    assert len(result2) == 0

    # Verify caches are independent
    assert key1 in builder._cache
    assert key2 in builder._cache
    assert builder._cache[key1] == [bin1]
    assert builder._cache[key2] == []


# --- Test 6: empty repo returns empty list and caches it ---


@pytest.mark.asyncio
async def test_empty_repo_returns_empty_list_and_caches_it(
    builder: ClassPriorBuilder,
    repo: InMemoryShiftPredictorRepo,
    sample_key: EngineClassKey,
) -> None:
    """Read for a key with no rows -> returns []. Second read doesn't hit repo."""
    # First read
    result1 = await builder.read(sample_key)
    assert result1 == []

    # Second read (should still return [] without hitting repo again)
    result2 = await builder.read(sample_key)
    assert result2 == []

    # Both should be the same empty cached list
    assert sample_key in builder._cache
