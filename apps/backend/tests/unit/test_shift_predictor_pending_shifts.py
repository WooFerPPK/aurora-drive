"""Unit tests for ShiftPredictor's pending-shift queue.

The predictor must defer firing the ShiftEventListener until enough
post-shift frames have accumulated to compute residuals (FR-015 settling
delay + 200 ms measurement window). These tests pin that behavior:

1. Listener does NOT fire on the gear-change frame.
2. Listener does NOT fire while post_window is still filling.
3. Listener fires exactly when ``frames_needed`` frames have been added.
4. Concurrent pendings (a second shift before the first fills) progress
   independently.
5. ``flush()`` drains any leftover pendings even if their post_window is
   short (better to emit and let cleanliness checks reject downstream
   than to silently lose the event).
6. ``reset(fp)`` drops pending shifts for the reset fingerprint.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint
from fh6.domain.value_objects.ids import CarId, SessionId
from tests.contract.fake_repos import InMemoryShiftPredictorRepo
from tests.unit.test_shift_event_evaluator import _make_config

_FP = EngineFingerprint(car_ordinal=2451, performance_index=812, num_cylinders=6)
_SESSION = SessionId("test-session-pending-shifts")
_CAR = CarId("car-pending-shifts")
_BASE_TIME = datetime(2026, 5, 23, 10, 0, 0, tzinfo=UTC)


def _frame(*, gear: int, rpm: float, ts_ms: int) -> DecodedFrame:
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
        motion={
            "speed_mps": 41.0,
            "speed": 41.0,
            "velocity": {"x": 0.0, "y": 0.0, "z": 41.0},
            "acceleration": {"x": 0.0, "y": 0.0, "z": 2.0},
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
            "carOrdinal": _FP.car_ordinal,
            "carClass": "A",
            "carClassRaw": 0,
            "performanceIndex": _FP.performance_index,
            "numCylinders": _FP.num_cylinders,
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
    return DecodedFrame(
        session_id=_SESSION,
        car_id=_CAR,
        received_at=_BASE_TIME + timedelta(milliseconds=ts_ms),
        raw=raw,
    )


class _RecordingListener:
    """Captures every ``on_shift`` call (args + kwargs) for inspection."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def on_shift(
        self,
        session_id: Any,
        gear_from: int,
        gear_to: int,
        at: Any,
        pre_window: Any,
        post_window: Any,
        *,
        fingerprint: Any,
        bins_snapshot: Any,
        ratios_snapshot: Any,
        recommended_rpm: float | None,
        recommendation_conf: float | None,
    ) -> None:
        self.calls.append(
            {
                "session_id": session_id,
                "gear_from": gear_from,
                "gear_to": gear_to,
                "at": at,
                "pre_window": list(pre_window),
                "post_window": list(post_window),
                "fingerprint": fingerprint,
                "recommended_rpm": recommended_rpm,
                "recommendation_conf": recommendation_conf,
            }
        )


class _StubCurveResolver:
    def __init__(self) -> None:
        self._curves = ResolvedCurves(
            optimal_rpm_by_gear={3: 7100, 4: 7000},
            confidence_by_gear={3: 0.85, 4: 0.80},
            stage="learned",
            samples_by_gear_pair={(3, 4): 50, (4, 5): 30},
            by_gear_downshift={3: 4200, 4: 4800, 5: 5000},
            confidence_by_gear_downshift={3: 0.70, 4: 0.75, 5: 0.65},
        )

    def resolve(self, bins: Any, ratios: Any, idle_rpm: float, max_rpm: float) -> ResolvedCurves:
        return self._curves


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


def _build_predictor() -> tuple[ShiftPredictor, _RecordingListener, InMemoryShiftPredictorRepo]:
    cfg = _make_config(
        shift_warmup_seconds=0,
        shift_gear_stable_frames=1,
        shift_recompute_every_n=10_000,
    )
    repo = InMemoryShiftPredictorRepo()
    listener = _RecordingListener()
    predictor = ShiftPredictor(
        config=cfg,
        repo=repo,
        bin_trainer=BinTrainer(half_life_samples=cfg.shift_ewma_half_life_samples),
        ratio_kalman=RatioKalman(),
        curve_resolver=_StubCurveResolver(),
        class_prior=_StubClassPrior(),
        change_point=_StubChangePoint(),
        shift_listener=listener,
        transmission_mode_inferer=TransmissionModeInferer(config=cfg),
    )
    return predictor, listener, repo


@pytest.mark.asyncio
async def test_listener_does_not_fire_until_post_window_fills() -> None:
    """Drive 1 frame @ gear 3, 1 frame @ gear 4 (shift), then 19 more frames @ gear 4.
    The listener should fire on exactly the 20th post-shift frame."""
    predictor, listener, _ = _build_predictor()

    ts_ms = 0
    # Pre-shift frame at gear 3.
    await predictor.on_frame(
        _frame(gear=3, rpm=7100.0, ts_ms=ts_ms),
        session_uptime_s=1.0,
        session_type="race",
    )
    ts_ms += 33

    # Gear-change frame: prev_gear=3, current_gear=4 -> enqueue pending.
    await predictor.on_frame(
        _frame(gear=4, rpm=5800.0, ts_ms=ts_ms),
        session_uptime_s=2.0,
        session_type="race",
    )
    ts_ms += 33

    # 1 pending exists in state; listener has NOT fired.
    # Note: the gear-change frame itself is NOT in the post_window — the
    # drain step runs at the *start* of each on_frame call, so the shift
    # frame triggers enqueue only; the post_window starts empty.
    state = predictor._states[_FP]
    assert len(state.pending_shifts) == 1
    assert len(state.pending_shifts[0].post_window) == 0
    assert listener.calls == []

    # Drive 19 more frames -> 19 frames in post_window; still no fire.
    for _ in range(19):
        await predictor.on_frame(
            _frame(gear=4, rpm=5800.0, ts_ms=ts_ms),
            session_uptime_s=3.0 + ts_ms / 1000.0,
            session_type="race",
        )
        ts_ms += 33
    assert listener.calls == [], "should not fire until 20 post-shift frames"
    assert len(state.pending_shifts) == 1
    assert len(state.pending_shifts[0].post_window) == 19

    # Drive the 20th post-shift frame -> listener fires, pending drained.
    await predictor.on_frame(
        _frame(gear=4, rpm=5800.0, ts_ms=ts_ms),
        session_uptime_s=10.0,
        session_type="race",
    )
    assert len(listener.calls) == 1
    call = listener.calls[0]
    assert call["gear_from"] == 3
    assert call["gear_to"] == 4
    assert len(call["post_window"]) == 20
    assert len(state.pending_shifts) == 0


@pytest.mark.asyncio
async def test_listener_not_fired_with_only_partial_post_window() -> None:
    """Drive a shift then only 5 post-shift frames — listener must not fire."""
    predictor, listener, _ = _build_predictor()

    ts_ms = 0
    await predictor.on_frame(
        _frame(gear=3, rpm=7100.0, ts_ms=ts_ms),
        session_uptime_s=1.0,
        session_type="race",
    )
    ts_ms += 33
    # Shift frame (post_window=[this])
    await predictor.on_frame(
        _frame(gear=4, rpm=5800.0, ts_ms=ts_ms),
        session_uptime_s=2.0,
        session_type="race",
    )
    ts_ms += 33

    # 5 more frames -> 5 frames in post_window (the gear-change frame
    # itself doesn't enter post_window — drain runs before detection).
    for _ in range(5):
        await predictor.on_frame(
            _frame(gear=4, rpm=5800.0, ts_ms=ts_ms),
            session_uptime_s=3.0 + ts_ms / 1000.0,
            session_type="race",
        )
        ts_ms += 33

    assert listener.calls == []
    state = predictor._states[_FP]
    assert len(state.pending_shifts) == 1
    assert len(state.pending_shifts[0].post_window) == 5


@pytest.mark.asyncio
async def test_concurrent_pending_shifts_progress_independently() -> None:
    """A second shift before the first fills enqueues a second pending;
    each tracks its own post_window independently."""
    predictor, listener, _ = _build_predictor()

    ts_ms = 0
    # Prime gear 3.
    await predictor.on_frame(
        _frame(gear=3, rpm=7100.0, ts_ms=ts_ms),
        session_uptime_s=1.0,
        session_type="race",
    )
    ts_ms += 33
    # First shift: 3 -> 4.
    await predictor.on_frame(
        _frame(gear=4, rpm=5800.0, ts_ms=ts_ms),
        session_uptime_s=2.0,
        session_type="race",
    )
    ts_ms += 33

    # 5 more frames at gear 4 (pending #1 now has 6 frames in its post_window).
    for _ in range(5):
        await predictor.on_frame(
            _frame(gear=4, rpm=5800.0, ts_ms=ts_ms),
            session_uptime_s=3.0 + ts_ms / 1000.0,
            session_type="race",
        )
        ts_ms += 33

    # Second shift: 4 -> 5. Pending #2 enqueued. Pending #1 is still filling.
    await predictor.on_frame(
        _frame(gear=5, rpm=5400.0, ts_ms=ts_ms),
        session_uptime_s=5.0,
        session_type="race",
    )
    ts_ms += 33

    state = predictor._states[_FP]
    assert len(state.pending_shifts) == 2
    # The drain step runs BEFORE shift detection on each frame, so the
    # second shift's gear-change frame is appended to pending #1's
    # post_window (drain step), then triggers enqueue of pending #2 with
    # an empty post_window.
    # Pending #1: 5 intermediate frames + the gear-5 shift frame = 6 frames.
    # Pending #2: just enqueued, post_window empty.
    assert len(state.pending_shifts[0].post_window) == 6
    assert state.pending_shifts[0].gear_from == 3
    assert state.pending_shifts[0].gear_to == 4
    assert len(state.pending_shifts[1].post_window) == 0
    assert state.pending_shifts[1].gear_from == 4
    assert state.pending_shifts[1].gear_to == 5

    # Drive 14 more frames so pending #1 reaches 20 frames and fires;
    # pending #2 will be sitting at 14 frames.
    for _ in range(14):
        await predictor.on_frame(
            _frame(gear=5, rpm=5400.0, ts_ms=ts_ms),
            session_uptime_s=6.0 + ts_ms / 1000.0,
            session_type="race",
        )
        ts_ms += 33

    assert len(listener.calls) == 1
    assert listener.calls[0]["gear_from"] == 3
    assert listener.calls[0]["gear_to"] == 4
    assert len(state.pending_shifts) == 1
    assert state.pending_shifts[0].gear_from == 4
    # pending #2 has 14 frames.
    assert len(state.pending_shifts[0].post_window) == 14

    # Six more frames -> pending #2 also fires.
    for _ in range(6):
        await predictor.on_frame(
            _frame(gear=5, rpm=5400.0, ts_ms=ts_ms),
            session_uptime_s=10.0 + ts_ms / 1000.0,
            session_type="race",
        )
        ts_ms += 33

    assert len(listener.calls) == 2
    assert listener.calls[1]["gear_from"] == 4
    assert listener.calls[1]["gear_to"] == 5
    assert len(state.pending_shifts) == 0


@pytest.mark.asyncio
async def test_flush_drains_remaining_pending_shifts() -> None:
    """``flush()`` fires any leftover pending shifts even if post_window is
    shorter than ``frames_needed`` — better to emit than to lose the event."""
    predictor, listener, _ = _build_predictor()

    ts_ms = 0
    await predictor.on_frame(
        _frame(gear=3, rpm=7100.0, ts_ms=ts_ms),
        session_uptime_s=1.0,
        session_type="race",
    )
    ts_ms += 33
    # Enqueue a pending shift.
    await predictor.on_frame(
        _frame(gear=4, rpm=5800.0, ts_ms=ts_ms),
        session_uptime_s=2.0,
        session_type="race",
    )

    assert len(predictor._states[_FP].pending_shifts) == 1
    assert listener.calls == []

    await predictor.flush()

    assert len(listener.calls) == 1
    assert listener.calls[0]["gear_from"] == 3
    assert listener.calls[0]["gear_to"] == 4
    # Pending was drained at flush time.
    assert len(predictor._states[_FP].pending_shifts) == 0


@pytest.mark.asyncio
async def test_reset_drops_pending_shifts_for_fingerprint() -> None:
    """``reset(fp)`` clears the fingerprint state, which drops its pending
    shifts. After reset the listener never fires for the cleared pendings."""
    predictor, listener, _ = _build_predictor()

    ts_ms = 0
    await predictor.on_frame(
        _frame(gear=3, rpm=7100.0, ts_ms=ts_ms),
        session_uptime_s=1.0,
        session_type="race",
    )
    ts_ms += 33
    await predictor.on_frame(
        _frame(gear=4, rpm=5800.0, ts_ms=ts_ms),
        session_uptime_s=2.0,
        session_type="race",
    )

    assert len(predictor._states[_FP].pending_shifts) == 1

    await predictor.reset(_FP)

    # State is gone entirely; no listener call.
    assert _FP not in predictor._states
    assert listener.calls == []
