"""Unit tests for ShiftPredictor session-scoped assist-intervention counters (FR-039, FR-040).

Drives synthetic eligible / intervened frames through ShiftPredictor.on_frame and
asserts on the assist_intervention block in the returned ShiftFrameDecoration.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from fh6.application.services.shift.bin_trainer import BinTrainer
from fh6.application.services.shift.ratio_kalman import RatioKalman
from fh6.application.services.shift.shift_predictor import (
    ResolvedCurves,
    ShiftFrameDecoration,
    ShiftPredictor,
)
from fh6.application.services.shift.transmission_mode import TransmissionModeInferer
from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.domain.value_objects.engine_fingerprint import (
    EngineClassKey,
    EngineFingerprint,
)
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.infrastructure.config import AppConfig
from tests.contract.fake_repos import InMemoryShiftPredictorRepo

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_FP = EngineFingerprint(car_ordinal=3101, performance_index=815, num_cylinders=6)
_CLASS_KEY = EngineClassKey(
    car_class="A",
    car_group=18,
    drivetrain_type="AWD",
    num_cylinders=6,
)
_NOW = datetime(2026, 5, 23, 10, 0, 0, tzinfo=UTC)
_SESSION = SessionId("test-session-assist")
_CAR = CarId("car-assist")


def _make_config(**overrides: Any) -> AppConfig:
    defaults: dict[str, Any] = dict(
        listen_addr="127.0.0.1",
        listen_port=5302,
        http_host="127.0.0.1",
        http_port=8000,
        db_dsn="postgresql+asyncpg://fh6:fh6@127.0.0.1:5432/fh6",
        llm_dry_run=False,
        log_level="INFO",
        log_format="pretty",
        rewind_continuity_threshold_m=20.0,
        rewind_match_tolerance_m=5.0,
        rewind_yaw_tolerance_rad=1.5708,
        rewind_pause_floor_ms=250,
        shift_throttle_min=0.95,
        shift_brake_max=0.05,
        shift_steer_max=0.10,
        shift_combined_slip_max=0.20,
        shift_gear_stable_frames=1,
        shift_warmup_seconds=0,
        shift_boost_settle_psi_per_s=1.0,
        shift_ewma_half_life_samples=54000,
        shift_bin_min_count=10,
        shift_pair_learned_samples=200,
        shift_change_z_threshold=3.0,
        shift_change_bins_required=3,
        shift_recompute_every_n=10_000,  # avoid heavy curve recompute work
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


def _frame(*, slip: float = 0.05, is_race_on: bool = True) -> DecodedFrame:
    """A frame that passes FR-003 clauses 1-9 (race on, no drift, warmup
    cleared at uptime=120s, throttle high, brake/clutch/steer zero, gear=3
    positive and stable with shift_gear_stable_frames=1).

    `slip` controls clause 11. With slip < 0.20 the frame is eligible.
    With slip = 0.60 (above tcs_slip_threshold=0.50) the filter rejects with
    reason="assist_intervention" and intervention_suspected=True.
    """
    raw = FrameRaw(
        is_race_on=is_race_on,
        timestamp_ms=1_000_000,
        engine={
            "rpm": 6000.0,
            "currentRpm": 6000.0,
            "maxRpm": 8000.0,
            "idleRpm": 900.0,
            "torque": 400.0,
            "torque_nm": 400.0,
            "boost": 0.0,
            "boost_psi": 0.0,
            "power_w": 250_000.0,
            "fuel": 0.5,
        },
        drivetrain={"gear": 3, "clutch": 0.0, "type": "AWD"},
        motion={"speed": 40.0, "speed_mps": 40.0},
        inputs={
            "throttle": 0.99,
            "brake": 0.0,
            "clutch": 0.0,
            "handbrake": 0.0,
            "steer": 0.0,
            "drivingLine": 0.0,
            "aiBrakeDelta": 0.0,
        },
        wheels={
            wn: {
                "slipRatio": 0.0,
                "slipAngle": 0.0,
                "combinedSlip": slip,
                "rotation_rad_s": 0.0,
                "suspensionTravel_norm": 0.5,
                "suspensionTravel_m": 0.07,
                "tireTemp_c": 80.0,
                "tireTemp_normWindow": 0.5,
                "onRumble": 0,
                "inPuddle": 0,
                "surfaceRumble": 0.0,
            }
            for wn in ("fl", "fr", "rl", "rr")
        },
        world={
            "carOrdinal": _FP.car_ordinal,
            "carClass": _CLASS_KEY.car_class,
            "carClassRaw": 0,
            "performanceIndex": _FP.performance_index,
            "numCylinders": _FP.num_cylinders,
            "carGroup": _CLASS_KEY.car_group,
            "smashableVelDiff": 0.0,
            "smashableMass": 0.0,
            "distanceTraveled": 0.0,
        },
        race={
            "lap": 1,
            "position": 1,
            "currentLapS": 12.0,
            "lastLapS": None,
            "bestLapS": None,
            "raceTimeS": 30.0,
        },
        tail_reserved_byte=0,
    )
    return DecodedFrame(
        session_id=_SESSION,
        car_id=_CAR,
        received_at=_NOW,
        raw=raw,
    )


# ---------------------------------------------------------------------------
# Stub collaborators
# ---------------------------------------------------------------------------


class _StubCurveResolver:
    def __init__(self) -> None:
        self.calls = 0

    def resolve(self, bins: Any, ratios: Any, idle_rpm: float, max_rpm: float) -> ResolvedCurves:
        self.calls += 1
        return ResolvedCurves(
            optimal_rpm_by_gear={3: 7100},
            confidence_by_gear={3: 0.8},
            stage="learned",
            samples_by_gear_pair={(3, 4): 1},
        )


class _StubClassPrior:
    def __init__(self) -> None:
        self.read_calls: list[Any] = []

    async def read(self, key: Any) -> list:
        self.read_calls.append(key)
        return []  # cold start — no priors

    async def maybe_rebuild(self, key: Any, contributing_fp: Any, **kwargs: Any) -> None:
        return None


class _StubChangePoint:
    def observe(self, *args: Any, **kwargs: Any) -> None:
        return None

    def reset(self, fp: Any) -> None:
        return None

    def is_paused(self, fp: Any) -> bool:
        return False


class _StubShiftListener:
    async def on_shift(self, *args: Any, **kwargs: Any) -> None:
        return None


def _make_predictor(cfg: AppConfig | None = None) -> ShiftPredictor:
    cfg = cfg or _make_config()
    return ShiftPredictor(
        config=cfg,
        repo=InMemoryShiftPredictorRepo(),
        bin_trainer=BinTrainer(half_life_samples=cfg.shift_ewma_half_life_samples),
        ratio_kalman=RatioKalman(),
        curve_resolver=_StubCurveResolver(),
        class_prior=_StubClassPrior(),
        change_point=_StubChangePoint(),
        shift_listener=_StubShiftListener(),
        transmission_mode_inferer=TransmissionModeInferer(config=cfg),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assist_counter_session_and_recent_pct_with_active_alert() -> None:
    """After 1000 eligible + 50 intervened (slip=0.6) frames, the decoration
    carries an assist_intervention block with session_pct ~= 50/1050,
    recent_pct ~= 50/900 (recent ring caps at 900), and active=True
    (recent_pct >= shift_assist_alert_pct=0.05).
    """
    predictor = _make_predictor()

    last_deco: ShiftFrameDecoration | None = None
    # 1000 eligible frames
    for _ in range(1000):
        last_deco = await predictor.on_frame(
            _frame(slip=0.05),
            session_uptime_s=120.0,
            session_type="race",
        )
    # 50 intervention frames (slip=0.6 > tcs_slip_threshold=0.50)
    for _ in range(50):
        last_deco = await predictor.on_frame(
            _frame(slip=0.6),
            session_uptime_s=120.0,
            session_type="race",
        )

    assert last_deco is not None
    ai = last_deco.assist_intervention
    assert ai is not None, "assist_intervention block should be populated after 1050 frames"
    assert ai.session_pct == pytest.approx(50 / 1050, abs=1e-4)
    # Recent ring caps at 900. After 1050 frames the ring holds the last 900
    # frames: 850 eligible + 50 intervened = 50 / 900.
    assert ai.recent_pct == pytest.approx(50 / 900, abs=1e-4)
    assert ai.active is True


@pytest.mark.asyncio
async def test_assist_block_omitted_below_floor_in_wire() -> None:
    """FR-040 floor: with fewer than 100 eligible-or-intervened frames, the
    assist_intervention block is None and the to_wire() dict omits the
    `assistIntervention` key.
    """
    predictor = _make_predictor()

    last_deco: ShiftFrameDecoration | None = None
    for _ in range(99):
        last_deco = await predictor.on_frame(
            _frame(slip=0.05),
            session_uptime_s=120.0,
            session_type="race",
        )

    assert last_deco is not None
    assert last_deco.assist_intervention is None
    wire = last_deco.to_wire()
    assert "assistIntervention" not in wire


@pytest.mark.asyncio
async def test_assist_block_present_at_floor_in_wire() -> None:
    """At exactly 100 eligible-or-intervened frames, the assist_intervention
    block is populated and the to_wire() dict contains an `assistIntervention`
    key with the expected camelCase subfields.
    """
    predictor = _make_predictor()

    last_deco: ShiftFrameDecoration | None = None
    for _ in range(100):
        last_deco = await predictor.on_frame(
            _frame(slip=0.05),
            session_uptime_s=120.0,
            session_type="race",
        )

    assert last_deco is not None
    assert last_deco.assist_intervention is not None
    wire = last_deco.to_wire()
    assert "assistIntervention" in wire
    block = wire["assistIntervention"]
    assert set(block.keys()) == {"recentPct", "sessionPct", "active"}
    # No interventions -> active False
    assert block["active"] is False
    assert block["sessionPct"] == pytest.approx(0.0)
    assert block["recentPct"] == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_drift_session_does_not_advance_assist_counters() -> None:
    """Drift session frames fail FR-003 clause 2 (drift) — those rejects must
    NOT advance the assist-intervention counters. After 200 drift frames the
    counters are still below the 100-frame floor *for an eligible session*,
    because no eligible-or-intervened frames have been recorded.
    """
    predictor = _make_predictor()

    last_deco: ShiftFrameDecoration | None = None
    for _ in range(200):
        last_deco = await predictor.on_frame(
            _frame(slip=0.05),
            session_uptime_s=120.0,
            session_type="drift",
        )

    assert last_deco is not None
    # Counters did not advance -> assist_intervention block is None.
    assert last_deco.assist_intervention is None


@pytest.mark.asyncio
async def test_on_session_started_resets_assist_counters() -> None:
    """on_session_started() drops the accumulated assist counters for that
    session so that the next session starts fresh.
    """
    predictor = _make_predictor()

    # Drive enough frames to accumulate counters past the 100-frame floor.
    for _ in range(150):
        await predictor.on_frame(
            _frame(slip=0.05),
            session_uptime_s=120.0,
            session_type="race",
        )

    # Counters exist and are past the floor.
    assert _SESSION in predictor._assist_stats
    assert predictor._assist_stats[_SESSION].eligible_or_intervened_frames > 0

    # Simulate the session manager signalling a new session.
    predictor.on_session_started(_SESSION)

    # The entry must be gone — next frame will start a fresh counter.
    assert _SESSION not in predictor._assist_stats
