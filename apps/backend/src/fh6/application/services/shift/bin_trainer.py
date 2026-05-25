"""BinTrainer — in-memory engine-curve estimator (FR-004, FR-005).

Maintains running statistics per (EngineFingerprint, gear, RPM bin):

1. Welford's running mean and variance — numerically stable, single-pass.
2. P² algorithm 90th-percentile — online quantile estimation (Jain & Chlamtac 1985).
3. EWMA decay — accumulators scaled by exp(-1 / half_life_samples) before each
   update so old data fades and the estimator adapts to engine retunes.

Process-local (no async state). Hydrate/flush methods provide repo round-trips.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fh6.domain.ports.shift_predictor_repo import BinRecord, ShiftPredictorRepository
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint

# P² algorithm: Jain & Chlamtac 1985
# Target percentile p = 0.90.
# Marker desired positions (fractions): [0, p/2, p, (1+p)/2, 1]
_P2_P = 0.90
_P2_DN = [0.0, _P2_P / 2.0, _P2_P, (1.0 + _P2_P) / 2.0, 1.0]

# ---------------------------------------------------------------------------
# Internal mutable bin state
# ---------------------------------------------------------------------------


@dataclass
class _BinState:
    """Mutable running statistics for a single (fingerprint, gear, rpm_bin).

    All fields are private to BinTrainer; external code sees only BinRecord
    via snapshot().
    """

    # --- Welford ---
    count: float = 0.0  # effective count (fractional due to EWMA)
    mean: float = 0.0  # running mean (torque_nm)
    M2: float = 0.0  # running sum of squared deviations

    # --- P² 90th-percentile ---
    # Bootstrap phase: first 5 samples stored directly, then markers initialised.
    _bootstrap: list[float] = field(default_factory=list)
    _p2_ready: bool = False
    # Marker heights q[0..4] represent 0, 45, 90, 95, 100 percentiles.
    _q: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0, 0.0])
    # Integer positions of each marker in the sample stream.
    _n: list[float] = field(default_factory=lambda: [1.0, 2.0, 3.0, 4.0, 5.0])
    # Desired positions (updated by dn each step).
    _nd: list[float] = field(
        default_factory=lambda: [
            1.0,
            1.0 + 2.0 * _P2_DN[1],
            1.0 + 2.0 * _P2_DN[2],
            1.0 + 2.0 * _P2_DN[3],
            5.0,
        ]
    )

    # --- Boost running mean (Welford) ---
    mean_boost: float = 0.0

    # --- Metadata ---
    last_updated: datetime = field(default_factory=lambda: datetime.min.replace(tzinfo=UTC))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _rpm_bin(rpm: float) -> int:
    """Map an RPM value to its 100-wide bin index."""
    return math.floor(rpm / 100.0)


def _parabolic(q: list[float], n: list[float], i: int, d: float) -> float:
    """P² parabolic (Piecewise-Parabolic) interpolation for marker i.

    Returns the adjusted height. Caller decides whether to use it.
    """
    # q[i-1], q[i], q[i+1] and positions n[i-1], n[i], n[i+1]
    qi = q[i]
    qm = q[i - 1]
    qp = q[i + 1]
    nm = n[i - 1]
    ni = n[i]
    np_ = n[i + 1]

    denom_left = ni - nm
    denom_right = np_ - ni

    # Guard against division by zero (shouldn't happen in normal flow)
    if denom_left == 0 or denom_right == 0:
        return qi + d * (qp - qm) / (np_ - nm) if np_ != nm else qi

    c1 = d / (np_ - nm)
    c2 = (ni - nm + d) * (qp - qi) / denom_right + (np_ - ni - d) * (qi - qm) / denom_left
    return qi + c1 * c2


def _linear(q: list[float], n: list[float], i: int, d: float) -> float:
    """P² linear interpolation as fallback for marker i."""
    if d > 0:
        return q[i] + d * (q[i + 1] - q[i]) / (n[i + 1] - n[i]) if n[i + 1] != n[i] else q[i]
    else:
        return q[i] + d * (q[i] - q[i - 1]) / (n[i] - n[i - 1]) if n[i] != n[i - 1] else q[i]


def _p2_update(state: _BinState, x: float) -> None:
    """Apply one P² update to the bin state for value x.

    The first 5 samples are stored in _bootstrap.  On the 5th sample the
    algorithm is initialised; from sample 6 onward the standard P² update
    applies.
    """
    # Bootstrap phase: collect the first 5 samples
    if not state._p2_ready:
        state._bootstrap.append(x)
        if len(state._bootstrap) == 5:
            # Initialise marker heights from sorted samples
            sorted_bs = sorted(state._bootstrap)
            state._q = list(sorted_bs)
            # Initial marker positions: 1, 2, 3, 4, 5
            state._n = [1.0, 2.0, 3.0, 4.0, 5.0]
            # Initial desired positions
            state._nd = [
                1.0,
                1.0 + 2.0 * _P2_DN[1],
                1.0 + 2.0 * _P2_DN[2],
                1.0 + 2.0 * _P2_DN[3],
                5.0,
            ]
            state._p2_ready = True
        return

    q = state._q
    n = state._n
    nd = state._nd

    # Step 1: Find cell k such that q[k] <= x < q[k+1]
    if x < q[0]:
        q[0] = x
        k = 0
    elif x < q[1]:
        k = 0
    elif x < q[2]:
        k = 1
    elif x < q[3]:
        k = 2
    elif x <= q[4]:
        k = 3
    else:
        q[4] = x
        k = 3

    # Step 2: Increment positions n[i] for all i > k
    for i in range(k + 1, 5):
        n[i] += 1.0

    # Increment desired positions by dn
    for i in range(5):
        nd[i] += _P2_DN[i]

    # Step 3: Adjust interior markers
    for i in range(1, 4):
        d = nd[i] - n[i]
        if (d >= 1.0 and n[i + 1] - n[i] > 1.0) or (d <= -1.0 and n[i - 1] - n[i] < -1.0):
            sign_d = 1.0 if d > 0 else -1.0
            # Parabolic prediction
            q_new = _parabolic(q, n, i, sign_d)
            # Fall back to linear if the parabolic result is out of order
            if q_new <= q[i - 1] or q_new >= q[i + 1]:
                q_new = _linear(q, n, i, sign_d)
            q[i] = q_new
            n[i] += sign_d


# ---------------------------------------------------------------------------
# BinTrainer
# ---------------------------------------------------------------------------


class BinTrainer:
    """In-memory engine-curve estimator with Welford + P² + EWMA.

    State is keyed by (EngineFingerprint, gear, rpm_bin). Bin indices are
    floor(rpm / 100).

    Typical lifecycle
    -----------------
    1. ``hydrate(fp, records)`` to load existing state from the repo.
    2. ``update(...)`` for each eligible frame.
    3. ``await flush(repo)`` periodically to persist.
    """

    def __init__(self, *, half_life_samples: int) -> None:
        if half_life_samples <= 0:
            raise ValueError("half_life_samples must be positive")
        self._half_life = half_life_samples
        # EWMA decay factor applied before each update.
        self._decay: float = math.exp(-1.0 / half_life_samples)
        # Flat state dict keyed by (EngineFingerprint, gear, rpm_bin).
        self._bins: dict[tuple[EngineFingerprint, int, int], _BinState] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(
        self,
        fp: EngineFingerprint,
        gear: int,
        rpm: float,
        torque_nm: float,
        boost_psi: float,
        at: datetime,
    ) -> None:
        """Record one eligible-frame sample.

        Applies EWMA decay to the bin's accumulators THEN performs the
        Welford + P² update.
        """
        bin_idx = _rpm_bin(rpm)
        key = (fp, gear, bin_idx)
        state = self._bins.get(key)
        if state is None:
            state = _BinState()
            self._bins[key] = state

        decay = self._decay

        # --- EWMA decay ---
        # Scale count and M2 (sum-of-squared-deviations) by the decay factor.
        # Mean is left unchanged: decay does not bias the mean, only reduces
        # the effective weight of older observations.
        state.count *= decay
        state.M2 *= decay

        # For P²: the marker heights (q[i]) and positions (n[i]) are NOT
        # decayed.  Decaying n[i] would accelerate marker movement (larger
        # n_desired - n gap) but in practice it biases the quantile estimate
        # because the desired-position increments dn are not scaled to match.
        # Acceptable simplification for v1: EWMA is expressed only through the
        # count/M2 Welford path; the P² estimator runs on the full unweighted
        # stream.  This means the q90 converges on a longer time scale than the
        # Welford mean, which is fine for the current use case.

        # --- Welford update ---
        state.count += 1.0
        delta = torque_nm - state.mean
        state.mean += delta / state.count
        delta2 = torque_nm - state.mean
        state.M2 += delta * delta2

        # --- P² update ---
        _p2_update(state, torque_nm)

        # --- Boost running mean (Welford, shares same effective count) ---
        # We maintain a separate boost mean.  The count is already updated
        # above; we use Welford's formula with the same count.
        boost_delta = boost_psi - state.mean_boost
        state.mean_boost += boost_delta / state.count

        # --- Metadata ---
        state.last_updated = max(state.last_updated, at)

    def snapshot(self, fp: EngineFingerprint) -> dict[tuple[int, int], BinRecord]:
        """Return a frozen snapshot of in-memory bins for this fingerprint.

        Keyed by (gear, rpm_bin). Each value is an immutable BinRecord.
        """
        result: dict[tuple[int, int], BinRecord] = {}
        for (f, gear, rpm_bin), state in self._bins.items():
            if f != fp:
                continue
            result[(gear, rpm_bin)] = self._state_to_record(fp, gear, rpm_bin, state)
        return result

    def hydrate(self, fp: EngineFingerprint, records: Sequence[BinRecord]) -> None:
        """Load bin state from the repo.

        Replaces any existing in-memory state for this fingerprint.
        """
        # Drop existing state for this fingerprint
        keys_to_remove = [k for k in self._bins if k[0] == fp]
        for k in keys_to_remove:
            del self._bins[k]

        for rec in records:
            state = _BinState(
                count=float(rec.count),
                mean=rec.mean_torque_nm,
                M2=rec.m2_torque,
                mean_boost=rec.mean_boost_psi,
                last_updated=rec.last_updated,
            )
            # Leave P² in bootstrap mode with no samples — on next real update
            # it will build fresh markers.  This is intentional: we only
            # persist q90 as a scalar (q[2]), not the full marker state, so
            # we cannot faithfully reconstruct the P² internals.  The q90 from
            # the record is preserved in the snapshot via direct injection below.
            # We inject the persisted q90 into the first bootstrap slot so that
            # the first snapshot after hydrate returns the correct value.
            # Actual P² tracking resumes once 5 new samples arrive.
            state._bootstrap = [rec.q90_torque_nm]
            # We also initialise q[2] directly so snapshot() reads the right q90
            # even before the bootstrap is complete.
            state._q[2] = rec.q90_torque_nm

            self._bins[(fp, rec.gear, rec.rpm_bin)] = state

    async def flush(self, repo: ShiftPredictorRepository) -> None:
        """Persist all in-memory bins via repo.upsert_bins.

        A snapshot is taken atomically before the async call; the trainer
        keeps its in-memory state after flushing.
        """
        records: list[BinRecord] = []
        for (fp, gear, rpm_bin), state in self._bins.items():
            records.append(self._state_to_record(fp, gear, rpm_bin, state))
        await repo.upsert_bins(records)

    def sample_count(self, fp: EngineFingerprint, gear: int) -> int:
        """Sum of ``count`` across all rpm_bins for this fingerprint+gear.

        Returns 0 if no data has been collected for this fp+gear.
        Used by the predictor to decide stage transitions.
        """
        total = 0.0
        for (f, g, _rpm_bin), state in self._bins.items():
            if f == fp and g == gear:
                total += state.count
        return int(total)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _q90(self, state: _BinState) -> float:
        """Extract the current q90 estimate from a bin state.

        During bootstrap (< 5 samples), returns the median of whatever
        samples have been collected (or the single sample if count == 1).
        After bootstrap, returns P² marker q[2].
        """
        if state._p2_ready:
            return state._q[2]

        # Bootstrap: return the rough 90th percentile from the collected samples.
        bs = sorted(state._bootstrap)
        if not bs:
            return 0.0
        # P90 index in sorted list
        idx = math.ceil(0.9 * len(bs)) - 1
        idx = max(0, min(idx, len(bs) - 1))
        return bs[idx]

    def _state_to_record(
        self,
        fp: EngineFingerprint,
        gear: int,
        rpm_bin: int,
        state: _BinState,
    ) -> BinRecord:
        """Convert internal _BinState to an immutable BinRecord."""
        return BinRecord(
            fingerprint=fp,
            gear=gear,
            rpm_bin=rpm_bin,
            count=int(state.count),
            mean_torque_nm=state.mean,
            m2_torque=state.M2,
            q90_torque_nm=self._q90(state),
            mean_boost_psi=state.mean_boost,
            last_updated=state.last_updated,
        )
