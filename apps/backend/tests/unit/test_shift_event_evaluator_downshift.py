"""Unit tests for ShiftEventEvaluator downshift handling (Task 15, FR-048).

Tests the downshift dispatch branch:
- Clean downshift writes one row with rev-match residual fields populated.
- Off-rev-match downshift produces an ``est_cost_s`` per the FR-048 formula.
- Dirty downshift (mid-shift throttle blip) writes no row.
- Downshift with no recommendation writes a row with NULL recommendation
  fields but still populates ``post_shift_rpm``.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from fh6.application.services.shift.curve_resolver import ShiftCurveResolver
from fh6.application.services.shift.shift_event_evaluator import ShiftEventEvaluator
from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.infrastructure.config import AppConfig
from tests.contract.fake_repos import InMemoryShiftPredictorRepo

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FP = EngineFingerprint(car_ordinal=2451, performance_index=812, num_cylinders=6)
_SESSION = SessionId("test-session-downshift")
_NOW = datetime(2026, 5, 23, 11, 0, 0, tzinfo=UTC)

IDLE_RPM = 900.0
MAX_RPM = 8000.0

# Downshift-friendly defaults: throttle lifted, brake engaged, straight, no slip.
_DOWN_INPUTS = {"throttle": 0.0, "brake": 0.4, "steer": 0.0, "clutch": 0.0}
_DOWN_VELOCITY = {"x": 30.0, "y": 0.0, "z": 0.0}
# Mild deceleration along motion (negative dot with v).
_DOWN_ACCELERATION = {"x": -3.0, "y": 0.0, "z": 0.0}


# ---------------------------------------------------------------------------
# Config helper (mirrors test_shift_event_evaluator.py)
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
# Frame builders (downshift-flavoured)
# ---------------------------------------------------------------------------


def _make_down_frame(
    *,
    throttle: float = 0.0,
    brake: float = 0.4,
    steer: float = 0.0,
    combined_slip: float = 0.05,
    boost: float = 0.0,
    rpm: float = 4800.0,
    gear: int = 3,
    velocity: dict[str, float] | None = None,
    acceleration: dict[str, float] | None = None,
    car_class: str = "A",
    received_at: datetime = _NOW,
) -> DecodedFrame:
    """Build a synthetic downshift-context DecodedFrame."""
    if velocity is None:
        velocity = dict(_DOWN_VELOCITY)
    if acceleration is None:
        acceleration = dict(_DOWN_ACCELERATION)

    raw = FrameRaw(
        is_race_on=True,
        timestamp_ms=1000,
        engine={
            "currentRpm": rpm,
            "maxRpm": MAX_RPM,
            "idleRpm": IDLE_RPM,
            "torque": 50.0,  # closed-throttle: low engine torque
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


def _down_window(
    n: int = 6,
    *,
    gear: int,
    rpm: float,
    throttle: float = 0.0,
    brake: float = 0.4,
    start: datetime = _NOW,
) -> list[DecodedFrame]:
    return [
        _make_down_frame(
            gear=gear,
            rpm=rpm,
            throttle=throttle,
            brake=brake,
            received_at=start + timedelta(milliseconds=i * 33),
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Fixtures
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
# Helper: invoke on_shift with downshift defaults
# ---------------------------------------------------------------------------


async def _call_downshift(
    evaluator: ShiftEventEvaluator,
    *,
    pre: list[DecodedFrame] | None = None,
    post: list[DecodedFrame] | None = None,
    gear_from: int = 3,
    gear_to: int = 2,
    ratio_from: float = 200.0,
    ratio_to: float = 260.0,
    recommended_rpm: float | None = 4800.0,
    recommendation_conf: float | None = 0.85,
) -> None:
    # Pre window: in gear_from at the pre-shift RPM (4800).
    if pre is None:
        pre = _down_window(6, gear=gear_from, rpm=4800.0)
    # Post window default supplied by callers (varies per scenario).
    if post is None:
        post = _down_window(
            6,
            gear=gear_to,
            rpm=6300.0,
            start=_NOW + timedelta(milliseconds=500),
        )

    # Build minimal ratio/bins snapshots. Bins are not used by the downshift
    # path (no torque residual), but the existing on_shift signature requires
    # both.
    from fh6.domain.ports.shift_predictor_repo import RatioRecord

    ratios_snapshot = {
        gear_from: RatioRecord(
            fingerprint=_FP,
            gear=gear_from,
            ratio=ratio_from,
            variance=0.01,
            last_updated=_NOW,
        ),
        gear_to: RatioRecord(
            fingerprint=_FP,
            gear=gear_to,
            ratio=ratio_to,
            variance=0.01,
            last_updated=_NOW,
        ),
    }

    await evaluator.on_shift(
        _SESSION,
        gear_from=gear_from,
        gear_to=gear_to,
        at=_NOW,
        pre_window=pre,
        post_window=post,
        fingerprint=_FP,
        bins_snapshot={},
        ratios_snapshot=ratios_snapshot,
        recommended_rpm=recommended_rpm,
        recommendation_conf=recommendation_conf,
    )


# ---------------------------------------------------------------------------
# Scenario 1: Clean downshift within rev-match band (delta ≤ 300)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_downshift_within_rev_match_band(
    evaluator: ShiftEventEvaluator,
    repo: InMemoryShiftPredictorRepo,
) -> None:
    """3→2 downshift, recommended pre=4800, ratios 200→260, post_rpm=6300.

    Expected recommended_post_rpm = 4800 * 260 / 200 = 6240.
    delta = 60 → within ±300 band → est_cost_s = 0.0.
    Predicted/measured torque are NULL (no propulsive model for downshifts).
    """
    await _call_downshift(evaluator)

    rows = await repo.read_shift_events(_SESSION)
    assert len(rows) == 1, f"Expected 1 row, got {len(rows)}"

    row = rows[0]
    assert row.gear_from == 3
    assert row.gear_to == 2
    assert row.recommended_rpm == pytest.approx(4800.0)
    assert row.post_shift_rpm == pytest.approx(6300.0)
    assert row.recommended_post_rpm == pytest.approx(6240.0)
    assert row.est_cost_s == pytest.approx(0.0)
    assert row.predicted_post_torque is None
    assert row.measured_post_torque is None


# ---------------------------------------------------------------------------
# Scenario 2: Downshift outside rev-match band → est_cost_s populated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_downshift_outside_band_populates_est_cost(
    evaluator: ShiftEventEvaluator,
    repo: InMemoryShiftPredictorRepo,
) -> None:
    """Same setup but post_rpm = 6700 → delta = 460 → est_cost = 0.008."""
    post = _down_window(
        6,
        gear=2,
        rpm=6700.0,
        start=_NOW + timedelta(milliseconds=500),
    )
    await _call_downshift(evaluator, post=post)

    rows = await repo.read_shift_events(_SESSION)
    assert len(rows) == 1, f"Expected 1 row, got {len(rows)}"

    row = rows[0]
    assert row.post_shift_rpm == pytest.approx(6700.0)
    assert row.recommended_post_rpm == pytest.approx(6240.0)
    # delta=460 → over=160 → 160/1000 * 0.05 = 0.008
    assert row.est_cost_s == pytest.approx(0.008)
    assert row.predicted_post_torque is None
    assert row.measured_post_torque is None


# ---------------------------------------------------------------------------
# Scenario 3: Dirty downshift (mid-shift throttle blip) → no row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dirty_downshift_throttle_blip_skipped(
    evaluator: ShiftEventEvaluator,
    repo: InMemoryShiftPredictorRepo,
) -> None:
    """A frame with throttle > 0.30 AND brake < 0.10 in the post window
    fails the clean-downshift gate (neither brake nor closed-throttle).
    """
    post = _down_window(
        6,
        gear=2,
        rpm=6300.0,
        start=_NOW + timedelta(milliseconds=500),
    )
    # Inject a throttle-on + brake-off frame partway through the post window.
    post[2] = _make_down_frame(
        gear=2,
        rpm=6300.0,
        throttle=0.5,
        brake=0.0,
        received_at=_NOW + timedelta(milliseconds=500 + 2 * 33),
    )

    await _call_downshift(evaluator, post=post)

    rows = await repo.read_shift_events(_SESSION)
    assert len(rows) == 0, "Throttle blip mid-downshift should reject the row"


# ---------------------------------------------------------------------------
# Scenario 4: Downshift with no recommendation → row written with NULLs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_downshift_no_recommendation_still_writes_row(
    evaluator: ShiftEventEvaluator,
    repo: InMemoryShiftPredictorRepo,
) -> None:
    """No predictor recommendation at shift moment → row still written with
    recommended_rpm=NULL, recommended_post_rpm=NULL, est_cost_s=NULL, but
    post_shift_rpm IS populated from the post-window.
    """
    await _call_downshift(
        evaluator,
        recommended_rpm=None,
        recommendation_conf=None,
    )

    rows = await repo.read_shift_events(_SESSION)
    assert len(rows) == 1, f"Expected 1 row even without recommendation, got {len(rows)}"

    row = rows[0]
    assert row.gear_from == 3
    assert row.gear_to == 2
    assert row.recommended_rpm is None
    assert row.recommended_post_rpm is None
    assert row.est_cost_s is None
    assert row.predicted_post_torque is None
    assert row.measured_post_torque is None
    # post_shift_rpm still populated from the window
    assert row.post_shift_rpm == pytest.approx(6300.0)
