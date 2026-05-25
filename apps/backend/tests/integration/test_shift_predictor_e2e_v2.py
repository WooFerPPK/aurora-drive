"""End-to-end: ShiftPredictor wires on_frame gear-change detection into
TransmissionModeInferer via on_shift_event (Task 11, FR-042).

Drives synthetic frames through ``predictor.on_frame(...)`` with repeated
gear-3 → gear-4 transitions at consistent pre-shift RPMs. Asserts that:

1. After the drive, the inferer's per-fingerprint ring buffer has accumulated
   samples (i.e. the gear-change detection in on_frame is actually invoking
   self.on_shift_event(...) — the missing wiring this task adds).
2. With enough consistent-RPM (low-stdev) upshifts, the decoration's
   ``transmission_mode`` block reports ``mode == "auto"`` with non-zero
   confidence (consistent shift points → automatic transmission).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from fh6.application.services.shift.bin_trainer import BinTrainer
from fh6.application.services.shift.ratio_kalman import RatioKalman
from fh6.application.services.shift.shift_predictor import (
    ResolvedCurves,
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
# Fixtures / helpers (mirrors test_shift_predictor_trans_mode.py)
# ---------------------------------------------------------------------------

_FP = EngineFingerprint(car_ordinal=4242, performance_index=800, num_cylinders=6)
_CLASS_KEY = EngineClassKey(
    car_class="A",
    car_group=18,
    drivetrain_type="AWD",
    num_cylinders=6,
)
_BASE_TIME = datetime(2026, 5, 23, 10, 0, 0, tzinfo=UTC)
_SESSION = SessionId("test-session-e2e-v2")
_CAR = CarId("car-e2e-v2")


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
        shift_recompute_every_n=10_000,
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


def _frame(*, gear: int, rpm: float, ts_ms: int) -> DecodedFrame:
    """One synthetic frame at the given gear/rpm. All other fields keep the
    inputs WOT-clean so frames pass FR-003 driver/session preconditions.
    """
    raw = FrameRaw(
        is_race_on=True,
        timestamp_ms=ts_ms,
        engine={
            "rpm": rpm,
            "currentRpm": rpm,
            "maxRpm": 8000.0,
            "idleRpm": 900.0,
            "torque": 400.0,
            "torque_nm": 400.0,
            "boost": 0.0,
            "boost_psi": 0.0,
            "power_w": 250_000.0,
            "fuel": 0.5,
        },
        drivetrain={"gear": gear, "clutch": 0.0, "type": "AWD"},
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
                "combinedSlip": 0.05,
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
        received_at=_BASE_TIME,
        raw=raw,
    )


# ---------------------------------------------------------------------------
# Stub collaborators (lifted from test_shift_predictor_trans_mode.py)
# ---------------------------------------------------------------------------


class _StubCurveResolver:
    def resolve(self, bins: Any, ratios: Any, idle_rpm: float, max_rpm: float) -> ResolvedCurves:
        return ResolvedCurves(
            optimal_rpm_by_gear={3: 7100, 4: 7100},
            confidence_by_gear={3: 0.8, 4: 0.8},
            stage="learned",
            samples_by_gear_pair={(3, 4): 1},
        )


class _StubClassPrior:
    async def read(self, key: Any) -> list:
        return []

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


def _make_predictor() -> ShiftPredictor:
    cfg = _make_config()
    repo = InMemoryShiftPredictorRepo()
    inferer = TransmissionModeInferer(config=cfg)
    return ShiftPredictor(
        config=cfg,
        repo=repo,
        bin_trainer=BinTrainer(half_life_samples=cfg.shift_ewma_half_life_samples),
        ratio_kalman=RatioKalman(),
        curve_resolver=_StubCurveResolver(),
        class_prior=_StubClassPrior(),
        change_point=_StubChangePoint(),
        shift_listener=_StubShiftListener(),
        transmission_mode_inferer=inferer,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_frame_gear_change_propagates_to_transmission_mode_inferer() -> None:
    """Drive frames through ``on_frame`` with repeated 3→4 upshifts. The
    transmission-mode inferer must accumulate samples — proving that the
    gear-change detection inside ``on_frame`` invokes ``on_shift_event``
    (the wiring this task adds).
    """
    predictor = _make_predictor()

    # 12 clean upshifts (3 → 4), pre-shift RPM clustered tightly around 7000.
    # Pattern per cycle: a few stable-gear-3 frames, then one gear-4 frame
    # (triggers shift detection in on_frame), then return to gear-3.
    ts_ms = 0
    pre_shift_rpms = [
        6995.0,
        7005.0,
        7000.0,
        6998.0,
        7002.0,
        7003.0,
        6997.0,
        7001.0,
        7004.0,
        6996.0,
        7000.0,
        6999.0,
    ]
    for cycle, pre_rpm in enumerate(pre_shift_rpms):
        # Stable gear-3 frames so the predictor's state.prev_gear settles to 3
        # and recent_frames carries the pre-shift RPM.
        for _ in range(3):
            await predictor.on_frame(
                _frame(gear=3, rpm=pre_rpm, ts_ms=ts_ms),
                session_uptime_s=10.0 + ts_ms / 1000.0,
                session_type="race",
            )
            ts_ms += 33
        # One gear-4 frame — triggers the 3→4 shift detection.
        await predictor.on_frame(
            _frame(gear=4, rpm=pre_rpm - 1200.0, ts_ms=ts_ms),
            session_uptime_s=10.0 + ts_ms / 1000.0,
            session_type="race",
        )
        ts_ms += 33
        # Drop back to gear 3 so the next cycle can re-trigger 3→4.
        await predictor.on_frame(
            _frame(gear=3, rpm=pre_rpm, ts_ms=ts_ms),
            session_uptime_s=10.0 + ts_ms / 1000.0,
            session_type="race",
        )
        ts_ms += 33

    # Inferer ring buffer must have accumulated samples for (3, 4).
    inferer = predictor._trans_mode  # internal access OK for an integration test
    pair_rings = inferer._rings.get(_FP, {})
    samples_34 = list(pair_rings.get((3, 4), ()))
    assert len(samples_34) >= 10, (
        f"expected ≥10 samples for (3,4) after 12 driven upshifts, got "
        f"{len(samples_34)} (samples={samples_34!r}). This proves on_frame "
        f"is invoking on_shift_event."
    )

    # Touched-set must include the fingerprint (used by flush()).
    assert _FP in predictor._trans_mode_touched

    # Decoration must report a non-default transmission_mode block.
    # All pre-shift RPMs hovered within ±5 of 7000 — stdev ≈ 3 rpm, well below
    # the 50-rpm threshold → classification "auto".
    decoration = await predictor.on_frame(
        _frame(gear=3, rpm=7000.0, ts_ms=ts_ms),
        session_uptime_s=10.0 + ts_ms / 1000.0,
        session_type="race",
    )
    assert decoration.transmission_mode.mode == "auto", (
        f"expected mode='auto' from tight-RPM upshifts, got "
        f"{decoration.transmission_mode.mode!r} "
        f"(confidence={decoration.transmission_mode.confidence})"
    )
    assert decoration.transmission_mode.confidence > 0.0


@pytest.mark.asyncio
async def test_on_frame_does_not_propagate_when_gear_unchanged() -> None:
    """Sanity check: stable-gear frames produce no inferer samples."""
    predictor = _make_predictor()

    ts_ms = 0
    for _ in range(20):
        await predictor.on_frame(
            _frame(gear=3, rpm=7000.0, ts_ms=ts_ms),
            session_uptime_s=10.0 + ts_ms / 1000.0,
            session_type="race",
        )
        ts_ms += 33

    inferer = predictor._trans_mode
    pair_rings = inferer._rings.get(_FP, {})
    total_samples = sum(len(r) for r in pair_rings.values())
    assert total_samples == 0, f"no gear changes → no inferer samples expected, got {total_samples}"
