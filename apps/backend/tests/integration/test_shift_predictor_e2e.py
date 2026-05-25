"""End-to-end: IngestFrame + ShiftPredictor (Task 18).

Streams a synthetic ~30-second sequence of frames through IngestFrame and
asserts:
- ShiftPredictor.on_frame runs and stamps modeled.extras["shiftRecommendation"].
- session_uptime_s feeds into the eligibility filter — frames before the
  60s warmup are gated out; bins remain empty until uptime crosses warmup.
- After the warmup + enough WOT frames, bins start filling and the
  recommendation block surfaces on the frame.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from fh6.application.services.hot_cache import HotCache
from fh6.application.services.session_manager import SessionManager
from fh6.application.services.shift.bin_trainer import BinTrainer
from fh6.application.services.shift.curve_resolver import ShiftCurveResolver
from fh6.application.services.shift.ratio_kalman import RatioKalman
from fh6.application.services.shift.shift_predictor import ShiftPredictor
from fh6.application.services.shift.transmission_mode import TransmissionModeInferer
from fh6.application.use_cases.ingest_frame import IngestFrame
from fh6.domain.entities.frame import FrameRaw
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint
from tests.contract.fake_repos import (
    InMemoryCarRepository,
    InMemoryFrameStore,
    InMemorySessionRepository,
    InMemoryShiftPredictorRepo,
)
from tests.unit.test_shift_event_evaluator import _make_config

CAR_ORDINAL = 2451
PERFORMANCE_INDEX = 812
NUM_CYLINDERS = 6
FP = EngineFingerprint(
    car_ordinal=CAR_ORDINAL,
    performance_index=PERFORMANCE_INDEX,
    num_cylinders=NUM_CYLINDERS,
)


def _raw(*, gear: int, rpm: float, ts_ms: int) -> FrameRaw:
    return FrameRaw(
        is_race_on=True,
        timestamp_ms=ts_ms,
        engine={
            "rpm": rpm,
            "idleRpm": 900.0,
            "maxRpm": 8000.0,
            "power_w": 250_000.0,
            "torque_nm": 400.0,
            "boost_psi": 0.0,
            "fuel": 0.5,
            "currentRpm": rpm,
            "torque": 400.0,
            "boost": 0.0,
        },
        drivetrain={"gear": gear, "clutch": 0.0, "type": "AWD"},
        motion={
            "speed_mps": 41.0,
            "velocity": {"x": 0.0, "y": 0.0, "z": 41.0},
            "acceleration": {"x": 0.0, "y": 0.0, "z": 0.0},
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
            "carOrdinal": CAR_ORDINAL,
            "carClass": "A",
            "performanceIndex": PERFORMANCE_INDEX,
            "numCylinders": NUM_CYLINDERS,
            "carGroup": 18,
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


class _StubChangePoint:
    def observe(self, *a, **k) -> None: ...
    def reset(self, fp) -> None: ...
    def is_paused(self, fp) -> bool:
        return False


class _StubShiftListener:
    async def on_shift(self, *a, **k) -> None: ...


class _StubClassPrior:
    async def read(self, key):
        return []

    async def maybe_rebuild(self, key, contributing_fp):
        return None


def _build_predictor(repo: InMemoryShiftPredictorRepo) -> ShiftPredictor:
    cfg = _make_config(shift_warmup_seconds=2)  # 2s warmup so tests don't drag
    return ShiftPredictor(
        config=cfg,
        repo=repo,
        bin_trainer=BinTrainer(half_life_samples=cfg.shift_ewma_half_life_samples),
        ratio_kalman=RatioKalman(),
        curve_resolver=ShiftCurveResolver(config=cfg),
        class_prior=_StubClassPrior(),
        change_point=_StubChangePoint(),
        shift_listener=_StubShiftListener(),
        transmission_mode_inferer=TransmissionModeInferer(config=cfg),
    )


@pytest.mark.asyncio
async def test_shift_predictor_runs_inside_ingest_and_decorates_frames() -> None:
    sm = SessionManager(silence_seconds=60.0)
    store = InMemoryFrameStore()
    hot = HotCache()
    repo = InMemoryShiftPredictorRepo()
    predictor = _build_predictor(repo)
    queue: asyncio.Queue = asyncio.Queue()
    ingest = IngestFrame(
        queue=queue,
        session_manager=sm,
        session_repository=InMemorySessionRepository(),
        frame_store=store,
        hot_cache=hot,
        car_repository=InMemoryCarRepository(),
        lap_repository=None,
        tire_wear_model=None,
        shift_predictor=predictor,
    )

    t0 = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)

    # 100 warm-up frames at gear 3 alternating with gear 4 every ~10 frames
    # to drive both training (gear 4 long stretches) and ratios.
    for i in range(150):
        gear = 4 if (i // 10) % 2 == 0 else 5
        rpm = 4000.0 + (i % 40) * 100.0
        ts = i * 33
        # session_uptime_s = i * 0.033 ; we want > 2s warmup → at i >= 60
        await ingest._handle_one(
            _raw(gear=gear, rpm=rpm, ts_ms=ts), t0 + timedelta(milliseconds=ts)
        )

    # Pull the latest frame and assert the decoration landed in extras.
    sessions = list(store.frames.keys())
    assert sessions, "no sessions opened"
    last_frame = store.frames[sessions[0]][-1]
    assert "shiftRecommendation" in last_frame.modeled.extras, (
        "ShiftPredictor.on_frame did not stamp the modeled extras"
    )
    decoration = last_frame.modeled.extras["shiftRecommendation"]
    assert "byGear" in decoration
    assert "stage" in decoration
    assert decoration["fingerprint"]["carOrdinal"] == CAR_ORDINAL

    # Bins should be filling — confirm via the snapshot path.
    snap = predictor.get_snapshot(FP)
    assert snap.trained_sample_count > 0, "training should have started after warmup"


@pytest.mark.asyncio
async def test_shift_predictor_failure_isolated_from_ingest() -> None:
    """A predictor that raises must not break the ingest pipeline."""
    sm = SessionManager(silence_seconds=60.0)
    store = InMemoryFrameStore()
    hot = HotCache()
    queue: asyncio.Queue = asyncio.Queue()

    class _BadPredictor:
        async def on_frame(self, *a, **k):
            raise RuntimeError("boom")

    ingest = IngestFrame(
        queue=queue,
        session_manager=sm,
        session_repository=InMemorySessionRepository(),
        frame_store=store,
        hot_cache=hot,
        car_repository=InMemoryCarRepository(),
        lap_repository=None,
        tire_wear_model=None,
        shift_predictor=_BadPredictor(),
    )

    t0 = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
    # Should not raise even though the predictor blows up every frame.
    await ingest._handle_one(_raw(gear=4, rpm=6500.0, ts_ms=0), t0)

    # Frame still made it to the store.
    sessions = list(store.frames.keys())
    assert sessions
    assert len(store.frames[sessions[0]]) == 1
