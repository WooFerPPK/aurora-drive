"""Unit tests for ShiftEventEvaluator (Task 12).

Tests cover FR-015 clean-shift criteria, torque residual computation,
and FR-017 guarantee that upsert_bin is never called.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

import pytest

from fh6.application.services.shift.curve_resolver import ShiftCurveResolver
from fh6.application.services.shift.shift_event_evaluator import ShiftEventEvaluator
from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.domain.ports.shift_predictor_repo import BinRecord, RatioRecord
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.infrastructure.config import AppConfig
from tests.contract.fake_repos import InMemoryShiftPredictorRepo

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FP = EngineFingerprint(car_ordinal=2451, performance_index=812, num_cylinders=6)
_SESSION = SessionId("test-session-evaluator")
_NOW = datetime(2026, 5, 23, 10, 0, 0, tzinfo=UTC)

IDLE_RPM = 900.0
MAX_RPM = 8000.0

# Typical "good" inputs: full throttle, no brake, straight, no slip
_GOOD_INPUTS = {"throttle": 0.99, "brake": 0.0, "steer": 0.0, "clutch": 0.0}

# A velocity vector giving ~20 m/s forward
_GOOD_VELOCITY = {"x": 20.0, "y": 0.0, "z": 0.0}
# A mild acceleration forward
_GOOD_ACCELERATION = {"x": 5.0, "y": 0.0, "z": 0.0}

# ---------------------------------------------------------------------------
# Config helper
# ---------------------------------------------------------------------------


def _make_config(**overrides: Any) -> AppConfig:
    defaults: dict[str, Any] = dict(
        listen_addr="127.0.0.1",
        listen_port=5302,
        http_host="127.0.0.1",
        http_port=8000,
        db_dsn="postgresql+asyncpg://fh6:fh6@127.0.0.1:5432/fh6",
        llm_dry_run=True,
        log_level="DEBUG",
        log_format="pretty",
        rewind_continuity_threshold_m=20.0,
        rewind_match_tolerance_m=5.0,
        rewind_yaw_tolerance_rad=math.pi / 2,
        rewind_pause_floor_ms=250,
        shift_throttle_min=0.95,
        shift_brake_max=0.05,
        shift_steer_max=0.10,
        shift_combined_slip_max=0.20,
        shift_gear_stable_frames=5,
        shift_warmup_seconds=60,
        shift_boost_settle_psi_per_s=1.0,
        shift_ewma_half_life_samples=54_000,
        shift_bin_min_count=10,
        shift_pair_learned_samples=200,
        shift_change_z_threshold=3.0,
        shift_change_bins_required=3,
        shift_recompute_every_n=50,
        shift_display_throttle_min=0.70,
        shift_turbo_residual_delay_ms=500,
        shift_na_residual_delay_ms=300,
        shift_residual_window_ms=200,
        shift_prior_rebuild_cooldown_s=300,
        shift_prior_min_fp_samples=1000,
        shift_tcs_slip_threshold=0.50,
        shift_tcs_torque_floor_ratio=0.85,
        shift_assist_alert_pct=0.05,
        shift_assist_recent_window=900,
        shift_trans_mode_ring_cap=30,
        shift_trans_mode_min_samples=10,
        shift_trans_mode_auto_stdev_rpm=50.0,
        shift_downshift_brake_display_min=0.10,
        shift_downshift_throttle_display_max=0.30,
    )
    defaults.update(overrides)
    return AppConfig(**defaults)


# ---------------------------------------------------------------------------
# Frame builders
# ---------------------------------------------------------------------------


def _make_frame(
    *,
    throttle: float = 0.99,
    brake: float = 0.0,
    steer: float = 0.0,
    combined_slip: float = 0.1,
    boost: float = 0.0,
    rpm: float = 6500.0,
    gear: int = 3,
    velocity: dict[str, float] | None = None,
    acceleration: dict[str, float] | None = None,
    car_class: str = "A",
    received_at: datetime = _NOW,
) -> DecodedFrame:
    """Build a synthetic DecodedFrame for evaluator tests."""
    if velocity is None:
        velocity = dict(_GOOD_VELOCITY)
    if acceleration is None:
        acceleration = dict(_GOOD_ACCELERATION)

    raw = FrameRaw(
        is_race_on=True,
        timestamp_ms=1000,
        engine={
            "currentRpm": rpm,
            "maxRpm": MAX_RPM,
            "idleRpm": IDLE_RPM,
            "torque": 400.0,
            "boost": boost,
        },
        drivetrain={"gear": gear, "type": "AWD"},
        motion={
            "velocity": velocity,
            "acceleration": acceleration,
            "speed": math.sqrt(sum(v**2 for v in velocity.values())),
        },
        inputs={
            "throttle": throttle,
            "brake": brake,
            "steer": steer,
            "clutch": 0.0,
        },
        wheels={
            "fl": {"combinedSlip": combined_slip},
            "fr": {"combinedSlip": combined_slip},
            "rl": {"combinedSlip": combined_slip},
            "rr": {"combinedSlip": combined_slip},
        },
        world={
            "carClass": car_class,
            "carOrdinal": _FP.car_ordinal,
            "performanceIndex": _FP.performance_index,
            "numCylinders": _FP.num_cylinders,
        },
        race={},
        tail_reserved_byte=0,
    )
    return DecodedFrame(
        session_id=_SESSION,
        car_id=CarId("car-001"),
        received_at=received_at,
        raw=raw,
    )


def _good_window(n: int = 6, gear: int = 3, boost: float = 0.0) -> list[DecodedFrame]:
    """Build a window of n clean frames."""
    base = _NOW
    return [
        _make_frame(
            gear=gear,
            boost=boost,
            received_at=datetime(
                base.year, base.month, base.day, base.hour, base.minute, base.second + i, tzinfo=UTC
            ),
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Bin/ratio snapshot builders
# ---------------------------------------------------------------------------


def _make_bin(
    gear: int,
    rpm_bin: int,
    q90: float,
    count: int = 50,
    m2: float = 100.0,
) -> BinRecord:
    return BinRecord(
        fingerprint=_FP,
        gear=gear,
        rpm_bin=rpm_bin,
        count=count,
        mean_torque_nm=q90 * 0.9,
        m2_torque=m2,
        q90_torque_nm=q90,
        mean_boost_psi=0.0,
        last_updated=_NOW,
    )


def _gaussian_torque(
    rpm: float, peak_rpm: float = 6000.0, sigma: float = 1500.0, peak: float = 400.0
) -> float:
    return peak * math.exp(-(((rpm - peak_rpm) / sigma) ** 2))


def _make_bins_snapshot(
    gear: int, rpm_range: tuple[int, int] = (20, 80)
) -> dict[tuple[int, int], BinRecord]:
    """Build a rich bins snapshot for 'gear' using a Gaussian torque curve."""
    snap: dict[tuple[int, int], BinRecord] = {}
    for rpm_bin in range(rpm_range[0], rpm_range[1] + 1):
        center = (rpm_bin + 0.5) * 100.0
        q90 = _gaussian_torque(center)
        snap[(gear, rpm_bin)] = _make_bin(gear=gear, rpm_bin=rpm_bin, q90=q90)
    return snap


def _make_ratio_snapshot(gear: int, ratio: float = 160.0) -> dict[int, RatioRecord]:
    return {
        gear: RatioRecord(
            fingerprint=_FP,
            gear=gear,
            ratio=ratio,
            variance=0.01,
            last_updated=_NOW,
        )
    }


# ---------------------------------------------------------------------------
# Evaluator fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def cfg() -> AppConfig:
    return _make_config()


@pytest.fixture
def repo() -> InMemoryShiftPredictorRepo:
    return InMemoryShiftPredictorRepo()


@pytest.fixture
def evaluator(cfg: AppConfig, repo: InMemoryShiftPredictorRepo) -> ShiftEventEvaluator:
    resolver = ShiftCurveResolver(config=cfg)
    return ShiftEventEvaluator(config=cfg, repo=repo, curve_resolver=resolver)


# ---------------------------------------------------------------------------
# Helper: run on_shift
# ---------------------------------------------------------------------------


async def _call_shift(
    evaluator: ShiftEventEvaluator,
    *,
    pre: list[DecodedFrame] | None = None,
    post: list[DecodedFrame] | None = None,
    gear_from: int = 3,
    gear_to: int = 4,
    bins_snapshot: dict | None = None,
    ratios_snapshot: dict | None = None,
    recommended_rpm: float | None = 6500.0,
    recommendation_conf: float | None = 0.85,
) -> None:
    if pre is None:
        pre = _good_window(6, gear=gear_from)
    if post is None:
        post = _good_window(6, gear=gear_to)
    if bins_snapshot is None:
        bins_snapshot = _make_bins_snapshot(gear_to)
    if ratios_snapshot is None:
        ratios_snapshot = _make_ratio_snapshot(gear_to)

    await evaluator.on_shift(
        _SESSION,
        gear_from=gear_from,
        gear_to=gear_to,
        at=_NOW,
        pre_window=pre,
        post_window=post,
        fingerprint=_FP,
        bins_snapshot=bins_snapshot,
        ratios_snapshot=ratios_snapshot,
        recommended_rpm=recommended_rpm,
        recommendation_conf=recommendation_conf,
    )


# ---------------------------------------------------------------------------
# Test 1: Clean shift writes one row with all fields populated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_shift_writes_one_row(
    evaluator: ShiftEventEvaluator,
    repo: InMemoryShiftPredictorRepo,
) -> None:
    """A fully clean shift should produce exactly one row in the repo."""
    await _call_shift(evaluator)

    rows = await repo.read_shift_events(_SESSION)
    assert len(rows) == 1, f"Expected 1 row, got {len(rows)}"

    row = rows[0]
    assert row.session_id == _SESSION
    assert row.gear_from == 3
    assert row.gear_to == 4
    assert row.actual_rpm > 0.0
    assert row.recommended_rpm == pytest.approx(6500.0)
    assert row.recommendation_conf == pytest.approx(0.85)
    assert row.predicted_post_torque is not None
    assert row.measured_post_torque is not None
    assert row.est_cost_s is not None
    assert 0.0 <= row.est_cost_s <= 0.20


# ---------------------------------------------------------------------------
# Test 2: Brake mid-shift skips
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_brake_in_post_window_skips(
    evaluator: ShiftEventEvaluator,
    repo: InMemoryShiftPredictorRepo,
) -> None:
    """One frame with high brake in post_window → no row written."""
    post = _good_window(6, gear=4)
    # Inject high brake into one frame
    bad_raw = FrameRaw(
        is_race_on=True,
        timestamp_ms=1000,
        engine={
            "currentRpm": 5000.0,
            "maxRpm": MAX_RPM,
            "idleRpm": IDLE_RPM,
            "torque": 400.0,
            "boost": 0.0,
        },
        drivetrain={"gear": 4},
        motion={
            "velocity": dict(_GOOD_VELOCITY),
            "acceleration": dict(_GOOD_ACCELERATION),
            "speed": 20.0,
        },
        inputs={"throttle": 0.99, "brake": 0.5, "steer": 0.0, "clutch": 0.0},
        wheels={
            "fl": {"combinedSlip": 0.1},
            "fr": {"combinedSlip": 0.1},
            "rl": {"combinedSlip": 0.1},
            "rr": {"combinedSlip": 0.1},
        },
        world={"carClass": "A", "carOrdinal": 2451, "performanceIndex": 812, "numCylinders": 6},
        race={},
        tail_reserved_byte=0,
    )
    post[2] = DecodedFrame(
        session_id=_SESSION, car_id=CarId("car-001"), received_at=_NOW, raw=bad_raw
    )

    await _call_shift(evaluator, post=post)

    rows = await repo.read_shift_events(_SESSION)
    assert len(rows) == 0, "Brake in post-window should prevent row from being written"


# ---------------------------------------------------------------------------
# Test 3: Steering input skips
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_steer_in_pre_window_skips(
    evaluator: ShiftEventEvaluator,
    repo: InMemoryShiftPredictorRepo,
) -> None:
    """One pre-window frame with large steer → no row written."""
    pre = _good_window(6, gear=3)
    pre[1] = _make_frame(steer=0.5, gear=3)

    await _call_shift(evaluator, pre=pre)

    rows = await repo.read_shift_events(_SESSION)
    assert len(rows) == 0, "Steer in pre-window should prevent row from being written"


# ---------------------------------------------------------------------------
# Test 4: Throttle dip skips
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_throttle_dip_in_post_window_skips(
    evaluator: ShiftEventEvaluator,
    repo: InMemoryShiftPredictorRepo,
) -> None:
    """One post-window frame with low throttle → no row written."""
    post = _good_window(6, gear=4)
    post[3] = _make_frame(throttle=0.5, gear=4)

    await _call_shift(evaluator, post=post)

    rows = await repo.read_shift_events(_SESSION)
    assert len(rows) == 0, "Throttle dip in post-window should prevent row from being written"


# ---------------------------------------------------------------------------
# Test 5: Slip skips
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slip_in_window_skips(
    evaluator: ShiftEventEvaluator,
    repo: InMemoryShiftPredictorRepo,
) -> None:
    """One frame with high combinedSlip on fl wheel → no row written."""
    post = _good_window(6, gear=4)
    # Build a frame with high fl slip
    slippy_frame = _make_frame(combined_slip=0.0, gear=4)  # base: low slip on all corners
    # Override just fl
    raw = slippy_frame.raw
    raw.wheels["fl"] = {"combinedSlip": 0.5}
    post[0] = slippy_frame

    await _call_shift(evaluator, post=post)

    rows = await repo.read_shift_events(_SESSION)
    assert len(rows) == 0, "High slip in post-window should prevent row from being written"


# ---------------------------------------------------------------------------
# Test 6: Too-short pre window skips
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_too_short_pre_window_skips(
    evaluator: ShiftEventEvaluator,
    repo: InMemoryShiftPredictorRepo,
) -> None:
    """pre_window with only 3 frames (< 5 minimum) → no row written."""
    pre = _good_window(3, gear=3)  # only 3 frames

    await _call_shift(evaluator, pre=pre)

    rows = await repo.read_shift_events(_SESSION)
    assert len(rows) == 0, "Short pre-window should prevent row from being written"


# ---------------------------------------------------------------------------
# Test 7: Speed too low skips
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_speed_too_low_skips(
    evaluator: ShiftEventEvaluator,
    repo: InMemoryShiftPredictorRepo,
) -> None:
    """All post-window frames with near-zero velocity → no row written."""
    # Build frames with sub-1mps speed
    slow_velocity = {"x": 0.0, "y": 0.0, "z": 0.5}  # |v| = 0.5 m/s < 1.0
    slow_frames = [
        _make_frame(velocity=slow_velocity, acceleration={"x": 1.0, "y": 0.0, "z": 0.0})
        for _ in range(6)
    ]

    await _call_shift(evaluator, post=slow_frames)

    rows = await repo.read_shift_events(_SESSION)
    assert len(rows) == 0, "Sub-1mps speed should prevent row from being written"


# ---------------------------------------------------------------------------
# Test 8: Insufficient bins for gear_to
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_insufficient_bins_writes_row_with_none_torques(
    evaluator: ShiftEventEvaluator,
    repo: InMemoryShiftPredictorRepo,
) -> None:
    """Clean shift but no bins for gear_to → row written with predicted=None, est_cost=None."""
    await _call_shift(
        evaluator,
        bins_snapshot={},  # no data at all
        ratios_snapshot={},
    )

    rows = await repo.read_shift_events(_SESSION)
    assert len(rows) == 1, "Even without curve data a row should be written"

    row = rows[0]
    assert row.predicted_post_torque is None
    assert row.est_cost_s is None
    # actual_rpm and measured_torque should still be populated
    assert row.actual_rpm > 0.0
    assert row.measured_post_torque is not None


# ---------------------------------------------------------------------------
# Test 9: recommended_rpm=None is allowed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recommended_rpm_none_is_allowed(
    evaluator: ShiftEventEvaluator,
    repo: InMemoryShiftPredictorRepo,
) -> None:
    """recommended_rpm=None should not prevent a clean shift from being recorded."""
    await _call_shift(evaluator, recommended_rpm=None, recommendation_conf=None)

    rows = await repo.read_shift_events(_SESSION)
    assert len(rows) == 1, "recommended_rpm=None should still write a row"

    row = rows[0]
    assert row.recommended_rpm is None
    assert row.recommendation_conf is None
    assert row.actual_rpm > 0.0


# ---------------------------------------------------------------------------
# Test 10: Turbo settling check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_turbo_unstable_boost_skips(
    evaluator: ShiftEventEvaluator,
    repo: InMemoryShiftPredictorRepo,
) -> None:
    """Post-window with boost jumping 2 → 15 psi (highly turbulent) is rejected."""
    from datetime import timedelta

    # Build post frames with rapid boost rise: 2 → 15 psi over ~1 second
    post_turbo: list[DecodedFrame] = []
    n = 6
    for i in range(n):
        t = _NOW + timedelta(milliseconds=i * 200)  # 200ms spacing → 1 second total
        boost_val = 2.0 + (13.0 * i / (n - 1))  # ramps 2 → 15 psi
        f = _make_frame(boost=boost_val, gear=4, received_at=t)
        post_turbo.append(f)

    await _call_shift(evaluator, post=post_turbo)

    rows = await repo.read_shift_events(_SESSION)
    assert len(rows) == 0, "Turbulent boost in post-window should prevent row from being written"


@pytest.mark.asyncio
async def test_turbo_stable_boost_accepted(
    evaluator: ShiftEventEvaluator,
    repo: InMemoryShiftPredictorRepo,
) -> None:
    """Post-window with stable boost (12 → 12.1 psi) should be accepted."""
    from datetime import timedelta

    post_stable: list[DecodedFrame] = []
    n = 6
    for i in range(n):
        t = _NOW + timedelta(milliseconds=i * 200)
        boost_val = 12.0 + (0.1 * i / (n - 1))  # 12.0 → 12.1 psi (stable)
        f = _make_frame(boost=boost_val, gear=4, received_at=t)
        post_stable.append(f)

    await _call_shift(evaluator, post=post_stable)

    rows = await repo.read_shift_events(_SESSION)
    assert len(rows) == 1, "Stable turbo boost should not reject the shift"


# ---------------------------------------------------------------------------
# Test 11: FR-017 guarantee — upsert_bin is never called
# ---------------------------------------------------------------------------


class _UpsertBinGuard(InMemoryShiftPredictorRepo):
    """Wrapped repo that raises if upsert_bin is ever called."""

    async def upsert_bin(self, rec: Any) -> None:  # type: ignore[override]
        raise AssertionError("FR-017 violation: ShiftEventEvaluator called upsert_bin!")

    async def upsert_bins(self, recs: Any) -> None:  # type: ignore[override]
        raise AssertionError("FR-017 violation: ShiftEventEvaluator called upsert_bins!")


@pytest.mark.asyncio
async def test_fr017_upsert_bin_never_called(cfg: AppConfig) -> None:
    """End-to-end clean shift with guarded repo — upsert_bin must never fire."""
    guard_repo = _UpsertBinGuard()
    resolver = ShiftCurveResolver(config=cfg)
    evaluator = ShiftEventEvaluator(config=cfg, repo=guard_repo, curve_resolver=resolver)

    # Should complete without raising
    await _call_shift(evaluator)

    rows = await guard_repo.read_shift_events(_SESSION)
    assert len(rows) == 1, "Expected one clean-shift row from guarded repo"
