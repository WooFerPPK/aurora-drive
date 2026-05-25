"""ClassPriorBuilder — lazy aggregator for class-level prior bins.

Maintains a process-local cache mapping EngineClassKey -> list[ClassPriorBin]
and rebuilds the per-class prior from engine_curves by aggregating across all
qualifying fingerprints within the class.

v2 (FR-035): ``maybe_rebuild`` walks the supplied candidate fingerprints,
filters them via ``repo.list_fingerprints_for_class_key`` (each candidate must
have at least ``min_total_samples`` rows across its bins), aggregates their
per-(gear, rpm_bin) ``q90_torque_nm`` weighted by ``count``, then upserts the
result via ``repo.upsert_class_prior_bin``. A per-key cooldown protects the
write path from pathological flush bursts.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from fh6.domain.ports.shift_predictor_repo import (
    ClassPriorBin,
    ShiftPredictorRepository,
)
from fh6.domain.value_objects.engine_fingerprint import (
    EngineClassKey,
    EngineFingerprint,
)


class ClassPriorBuilder:
    """Lazy reader and rebuilder of class-level prior bins.

    Implements the ClassPriorReader Protocol defined in shift_predictor.py.
    """

    def __init__(self, *, repo: ShiftPredictorRepository) -> None:
        """Initialize the builder with a ShiftPredictorRepository.

        Args:
            repo: Repository for reading/writing class prior bins.
        """
        self._repo = repo
        self._cache: dict[EngineClassKey, list[ClassPriorBin]] = {}
        self._dirty: set[EngineClassKey] = set()
        self._last_rebuilt: dict[EngineClassKey, datetime] = {}

    async def read(self, key: EngineClassKey) -> list[ClassPriorBin]:
        """Read the cached prior for the class key, fetching from the repo on cache miss.

        Returns the cached prior for the given key. If the key is not in the cache
        or has been marked dirty, fetches from the repo and updates the cache.
        Returns an empty list if the prior has not been built yet.

        Args:
            key: The EngineClassKey identifying the class.

        Returns:
            List of ClassPriorBin records for the key. May be empty.
        """
        # If key is in cache and not dirty, return cached value
        if key in self._cache and key not in self._dirty:
            return self._cache[key]

        # Cache miss or dirty: fetch from repo
        result = await self._repo.read_class_prior(key)

        # Update cache and clear dirty flag
        self._cache[key] = result
        self._dirty.discard(key)

        return result

    async def maybe_rebuild(
        self,
        key: EngineClassKey,
        contributing_fp: EngineFingerprint,
        *,
        candidate_fingerprints: Sequence[EngineFingerprint] | None = None,
        excluded_paused: set[EngineFingerprint] | None = None,
        cooldown_s: int = 300,
        min_total_samples: int = 1_000,
    ) -> None:
        """Aggregate engine_curves across qualifying fingerprints into class_priors.

        Walks ``candidate_fingerprints`` (less any in ``excluded_paused``), asks
        the repo which of those have at least ``min_total_samples`` rows worth of
        bin counts, then aggregates each (gear, rpm_bin) using a count-weighted
        mean of ``q90_torque_nm``. Result rows are upserted into class_priors and
        the per-key cache is invalidated so the next ``read()`` re-fetches.

        A per-key cooldown of ``cooldown_s`` seconds blocks back-to-back rebuilds.
        If ``candidate_fingerprints`` is None or empty (or every candidate is
        paused or below threshold), the call is a no-op other than marking the
        key dirty for the next read.

        Args:
            key: The EngineClassKey to rebuild.
            contributing_fp: The EngineFingerprint that triggered the rebuild
                (informational; the actual contributors are
                ``candidate_fingerprints``).
            candidate_fingerprints: Fingerprints that may contribute to this
                class. The caller is responsible for supplying only fingerprints
                whose class key matches ``key`` (engine_curves does not store
                class_key, so the repo cannot filter for us).
            excluded_paused: Fingerprints currently paused by the change-point
                observer (FR-012 extension); they are dropped before the
                qualification query.
            cooldown_s: Minimum seconds between successful rebuilds for the same
                key.
            min_total_samples: Minimum per-fingerprint bin-count total required
                to qualify as a contributor.
        """
        now = datetime.now(tz=UTC)
        last = self._last_rebuilt.get(key)
        if last is not None and (now - last).total_seconds() < cooldown_s:
            return

        if not candidate_fingerprints:
            # Nothing to rebuild from; preserve v1 dirty-flag behavior so the
            # next read() re-fetches whatever is currently persisted.
            self._dirty.add(key)
            return

        excluded = excluded_paused or set()
        pool = [fp for fp in candidate_fingerprints if fp not in excluded]
        if not pool:
            self._dirty.add(key)
            return

        qualifying = await self._repo.list_fingerprints_for_class_key(
            candidate_fingerprints=pool,
            min_total_samples=min_total_samples,
        )
        if not qualifying:
            return

        # Aggregate (q90, count) contributions per (gear, rpm_bin) across all
        # qualifying fingerprints.
        bins_by_key: dict[tuple[int, int], list[tuple[float, int]]] = {}
        for fp, _total in qualifying:
            for b in await self._repo.read_bins(fp):
                bins_by_key.setdefault((b.gear, b.rpm_bin), []).append((b.q90_torque_nm, b.count))

        for (gear, rpm_bin), contribs in bins_by_key.items():
            total_count = sum(c for _q, c in contribs)
            if total_count == 0:
                continue
            weighted_q90 = sum(q * c for q, c in contribs) / total_count
            await self._repo.upsert_class_prior_bin(
                ClassPriorBin(
                    class_key=key,
                    gear=gear,
                    rpm_bin=rpm_bin,
                    count=total_count,
                    q90_torque_nm=weighted_q90,
                    last_built=now,
                )
            )

        self._last_rebuilt[key] = now
        self._dirty.discard(key)
        # Force the next read() to re-fetch the freshly persisted rows.
        self._cache.pop(key, None)

    def invalidate(self, key: EngineClassKey) -> None:
        """Force-drop the cache entry for this key.

        Removes the key from both the cache and the dirty set, ensuring the next
        read() call will fetch fresh data from the repo.

        Args:
            key: The EngineClassKey to invalidate.
        """
        self._cache.pop(key, None)
        self._dirty.discard(key)
