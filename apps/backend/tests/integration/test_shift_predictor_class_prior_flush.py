"""Integration test: class-prior rebuild fires on session flush (FR-036).

Task 6 wires `ShiftPredictor.flush()` to invoke
`ClassPriorBuilder.maybe_rebuild` for every touched fingerprint that has
crossed the `shift_prior_min_fp_samples` threshold. This integration test
hydrates two fingerprints sharing one class key, drives a single frame
through `on_frame` so the predictor records the per-fingerprint
class-key mapping, then flushes and asserts the resulting class-prior
rows have been persisted with a `last_built` timestamp after the test
started.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from fh6.application.services.shift.bin_trainer import BinTrainer
from fh6.application.services.shift.class_prior import ClassPriorBuilder
from fh6.application.services.shift.curve_resolver import ShiftCurveResolver
from fh6.application.services.shift.ratio_kalman import RatioKalman
from fh6.application.services.shift.shift_predictor import ShiftPredictor
from fh6.application.services.shift.transmission_mode import TransmissionModeInferer
from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.domain.ports.shift_predictor_repo import BinRecord
from fh6.domain.value_objects.engine_fingerprint import (
    EngineClassKey,
    EngineFingerprint,
)
from tests.contract.fake_repos import InMemoryShiftPredictorRepo
from tests.unit.test_shift_event_evaluator import _make_config

# ---------------------------------------------------------------------------
# Two fingerprints sharing one class key
# ---------------------------------------------------------------------------

CAR_CLASS = "S"
CAR_GROUP = 1
DRIVETRAIN = "AWD"
NUM_CYL = 8

FP_A = EngineFingerprint(car_ordinal=4001, performance_index=900, num_cylinders=NUM_CYL)
FP_B = EngineFingerprint(car_ordinal=4002, performance_index=900, num_cylinders=NUM_CYL)
CLASS_KEY = EngineClassKey(
    car_class=CAR_CLASS,
    car_group=CAR_GROUP,
    drivetrain_type=DRIVETRAIN,
    num_cylinders=NUM_CYL,
)


def _raw_for(fp: EngineFingerprint, *, gear: int = 4, rpm: float = 6000.0) -> FrameRaw:
    return FrameRaw(
        is_race_on=True,
        timestamp_ms=1000,
        engine={
            "currentRpm": rpm,
            "maxRpm": 8000.0,
            "idleRpm": 900.0,
            "torque": 400.0,
            "boost": 0.0,
            "rpm": rpm,
            "power_w": 250_000.0,
            "torque_nm": 400.0,
            "boost_psi": 0.0,
            "fuel": 0.5,
        },
        drivetrain={"gear": gear, "clutch": 0.0, "type": DRIVETRAIN},
        motion={
            "speed": 41.0,
            "speed_mps": 41.0,
            "velocity": {"x": 0.0, "y": 0.0, "z": 41.0},
            "acceleration": {"x": 5.0, "y": 0.0, "z": 0.0},
            "angularVelocity": {"x": 0.0, "y": 0.0, "z": 0.0},
            "orientation": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
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
            "carOrdinal": fp.car_ordinal,
            "carClass": CAR_CLASS,
            "performanceIndex": fp.performance_index,
            "numCylinders": fp.num_cylinders,
            "carGroup": CAR_GROUP,
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


def _decoded(fp: EngineFingerprint, at: datetime) -> DecodedFrame:
    return DecodedFrame(
        raw=_raw_for(fp),
        received_at=at,
        session_id=None,
        car_id=None,
    )


class _StubChangePoint:
    """No-op change-point observer: never pauses any fingerprint."""

    def observe(self, *args: Any, **kwargs: Any) -> None:
        return None

    def reset(self, fp: EngineFingerprint) -> None:
        return None

    def is_paused(self, fp: EngineFingerprint) -> bool:
        return False


class _StubShiftListener:
    async def on_shift(self, *args: Any, **kwargs: Any) -> None:
        return None


async def _seed_bins(
    repo: InMemoryShiftPredictorRepo,
    fp: EngineFingerprint,
    *,
    total: int,
    q90: float = 420.0,
) -> None:
    """Spread `total` samples evenly across 6 gears x 5 rpm-bins (30 cells)."""
    per_cell = max(1, total // 30)
    now = datetime.now(tz=UTC)
    for gear in range(2, 8):  # gears 2..7
        for rpm_bin_offset in range(5):
            rpm_bin = 40 + rpm_bin_offset
            await repo.upsert_bin(
                BinRecord(
                    fingerprint=fp,
                    gear=gear,
                    rpm_bin=rpm_bin,
                    count=per_cell,
                    mean_torque_nm=q90 * 0.8,
                    m2_torque=0.0,
                    q90_torque_nm=q90,
                    mean_boost_psi=0.0,
                    last_updated=now,
                )
            )


@pytest.mark.asyncio
async def test_flush_triggers_class_prior_rebuild_for_qualifying_fingerprints() -> None:
    """After flush, the class-prior row set is populated with last_built > test_start."""
    test_start = datetime.now(tz=UTC) - timedelta(seconds=1)

    repo = InMemoryShiftPredictorRepo()
    # Hydrate FP_A with 1500 samples across multiple gears, FP_B with 1200.
    await _seed_bins(repo, FP_A, total=1500, q90=400.0)
    await _seed_bins(repo, FP_B, total=1200, q90=500.0)

    cfg = _make_config(
        shift_warmup_seconds=0,
        shift_prior_min_fp_samples=1000,
        shift_prior_rebuild_cooldown_s=0,
    )
    class_prior = ClassPriorBuilder(repo=repo)
    predictor = ShiftPredictor(
        config=cfg,
        repo=repo,
        bin_trainer=BinTrainer(half_life_samples=cfg.shift_ewma_half_life_samples),
        ratio_kalman=RatioKalman(),
        curve_resolver=ShiftCurveResolver(config=cfg),
        class_prior=class_prior,
        change_point=_StubChangePoint(),
        shift_listener=_StubShiftListener(),
        transmission_mode_inferer=TransmissionModeInferer(config=cfg),
    )

    # Hydrate the predictor's in-memory state from the persisted bins so
    # flush() sees these fingerprints.
    await predictor.hydrate_for_session(session_id=None, fingerprint=FP_A)  # type: ignore[arg-type]
    await predictor.hydrate_for_session(session_id=None, fingerprint=FP_B)  # type: ignore[arg-type]

    # Drive a single frame for each fingerprint so the predictor records
    # the class_key mapping in its per-fingerprint state.
    now = datetime.now(tz=UTC)
    await predictor.on_frame(
        _decoded(FP_A, now),
        session_uptime_s=5.0,
        session_type="circuit",
    )
    await predictor.on_frame(
        _decoded(FP_B, now),
        session_uptime_s=5.0,
        session_type="circuit",
    )

    # Flush — should spawn a class-prior rebuild for CLASS_KEY.
    await predictor.flush()

    # Exactly one class-key was touched; expect exactly one rebuild task.
    pending = predictor.pending_class_prior_rebuilds()
    assert len(pending) == 1, f"expected one class-prior rebuild task, got {len(pending)}"

    # Await the spawned task(s) deterministically — production callers
    # can fire-and-forget, but the test needs the rebuild to settle
    # before asserting on the repo.
    if pending:
        await asyncio.gather(*pending)

    rows = await repo.read_class_prior(CLASS_KEY)
    assert len(rows) >= 1, f"expected ≥1 class_prior row after flush, got {len(rows)}"
    for row in rows:
        assert row.last_built >= test_start, (
            f"row.last_built {row.last_built} should be after test_start {test_start}"
        )
        assert row.class_key == CLASS_KEY
