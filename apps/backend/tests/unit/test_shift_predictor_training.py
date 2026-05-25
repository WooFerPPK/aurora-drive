"""Unit tests for ShiftPredictor aggregate (Task 8).

Tests cover orchestration behavior only — math correctness is covered by
Tests 6 (BinTrainer) and 7 (RatioKalman).
"""

from __future__ import annotations

from collections.abc import Sequence
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
from fh6.domain.ports.shift_predictor_repo import (
    BinRecord,
    RatioRecord,
    ResetCounts,
)
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.infrastructure.config import AppConfig

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_FP_COMPLETE = EngineFingerprint(car_ordinal=2451, performance_index=812, num_cylinders=6)
_FP_INCOMPLETE = EngineFingerprint(car_ordinal=None, performance_index=812, num_cylinders=6)
_NOW = datetime(2026, 5, 23, 10, 0, 0, tzinfo=UTC)
_SESSION = SessionId("test-session-001")


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
        shift_gear_stable_frames=5,
        shift_warmup_seconds=60,
        shift_boost_settle_psi_per_s=1.0,
        shift_ewma_half_life_samples=54000,
        shift_bin_min_count=10,
        shift_pair_learned_samples=200,
        shift_change_z_threshold=3.0,
        shift_change_bins_required=3,
        shift_recompute_every_n=10,
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


def _make_frame_raw(
    *,
    car_ordinal: int | None = 2451,
    performance_index: int | None = 812,
    num_cylinders: int | None = 6,
    gear: int = 3,
    rpm: float = 6500.0,
    max_rpm: float = 8000.0,
    idle_rpm: float = 900.0,
    torque: float = 400.0,
    throttle: float = 0.99,
    brake: float = 0.0,
    clutch: float = 0.0,
    steer: float = 0.05,
    drive_clutch: float = 0.0,
    boost: float = 0.0,
    speed: float = 30.0,
    is_race_on: bool = True,
    combined_slip: float = 0.1,
) -> FrameRaw:
    world: dict[str, Any] = {}
    if car_ordinal is not None:
        world["carOrdinal"] = car_ordinal
    if performance_index is not None:
        world["performanceIndex"] = performance_index
    if num_cylinders is not None:
        world["numCylinders"] = num_cylinders
    world["maxRpm"] = max_rpm

    return FrameRaw(
        is_race_on=is_race_on,
        timestamp_ms=1000,
        engine={
            "currentRpm": rpm,
            "maxRpm": max_rpm,
            "idleRpm": idle_rpm,
            "torque": torque,
            "boost": boost,
        },
        drivetrain={
            "gear": gear,
            "clutch": drive_clutch,
        },
        motion={"speed": speed},
        inputs={
            "throttle": throttle,
            "brake": brake,
            "clutch": clutch,
            "steer": steer,
        },
        wheels={
            "fl": {"combinedSlip": combined_slip},
            "fr": {"combinedSlip": combined_slip},
            "rl": {"combinedSlip": combined_slip},
            "rr": {"combinedSlip": combined_slip},
        },
        world=world,
        race={},
        tail_reserved_byte=0,
    )


def _make_frame(raw: FrameRaw | None = None) -> DecodedFrame:
    if raw is None:
        raw = _make_frame_raw()
    return DecodedFrame(
        session_id=_SESSION,
        car_id=CarId("car-001"),
        received_at=_NOW,
        raw=raw,
    )


def _make_eligible_frame(gear: int = 3, rpm: float = 6500.0) -> DecodedFrame:
    """Make a frame that will pass the training filter."""
    return _make_frame(
        _make_frame_raw(
            gear=gear,
            rpm=rpm,
            throttle=0.99,
            brake=0.0,
            clutch=0.0,
            steer=0.05,
            drive_clutch=0.0,
            combined_slip=0.1,
            is_race_on=True,
        )
    )


# ---------------------------------------------------------------------------
# Stub collaborators
# ---------------------------------------------------------------------------

_DEFAULT_CURVES = ResolvedCurves(
    optimal_rpm_by_gear={3: 7100, 4: 7000, 5: 6900},
    confidence_by_gear={3: 0.8, 4: 0.7, 5: 0.65},
    stage="learned",
    samples_by_gear_pair={(3, 4): 187, (4, 5): 100, (5, 6): 0},
)


class StubCurveResolver:
    def __init__(self, returns: ResolvedCurves | None = None) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self._returns = returns or _DEFAULT_CURVES

    def resolve(self, bins: Any, ratios: Any, idle_rpm: float, max_rpm: float) -> ResolvedCurves:
        self.calls.append((bins, ratios, idle_rpm, max_rpm))
        return self._returns


class StubClassPrior:
    def __init__(self) -> None:
        self.read_calls: list[Any] = []
        self.rebuild_calls: list[Any] = []

    async def read(self, key: Any) -> list:
        self.read_calls.append(key)
        return []

    async def maybe_rebuild(self, key: Any, contributing_fp: Any) -> None:
        self.rebuild_calls.append((key, contributing_fp))


class StubChangePoint:
    def __init__(self, *, paused: bool = False) -> None:
        self.observe_calls: list[Any] = []
        self.reset_calls: list[Any] = []
        self._paused = paused

    def observe(
        self,
        fp: Any,
        gear: int,
        rpm: float,
        torque_nm: float,
        at: Any,
        stored_bin: Any,
    ) -> None:
        self.observe_calls.append((fp, gear, rpm, torque_nm, at, stored_bin))

    def reset(self, fp: Any) -> None:
        self.reset_calls.append(fp)

    def is_paused(self, fp: Any) -> bool:
        return self._paused


class StubShiftListener:
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
        **kwargs: Any,
    ) -> None:
        self.calls.append(
            dict(
                session_id=session_id,
                gear_from=gear_from,
                gear_to=gear_to,
                at=at,
                pre_window=pre_window,
                post_window=post_window,
                **kwargs,
            )
        )


class StubRepo:
    def __init__(self) -> None:
        self.bins: list[BinRecord] = []
        self.ratios: list[RatioRecord] = []
        self.upsert_bins_calls: list[Any] = []
        self.upsert_ratio_calls: list[Any] = []
        self.reset_calls: list[EngineFingerprint] = []
        self._reset_result = ResetCounts(engine_curves=3, gear_ratios=2, shift_events=1)

    async def upsert_bin(self, rec: BinRecord) -> None:
        pass

    async def upsert_bins(self, recs: Sequence[BinRecord]) -> None:
        self.upsert_bins_calls.append(list(recs))

    async def read_bins(self, fp: EngineFingerprint) -> list[BinRecord]:
        return [r for r in self.bins if r.fingerprint == fp]

    async def upsert_ratio(self, rec: RatioRecord) -> None:
        self.upsert_ratio_calls.append(rec)

    async def read_ratios(self, fp: EngineFingerprint) -> list[RatioRecord]:
        return [r for r in self.ratios if r.fingerprint == fp]

    async def upsert_class_prior_bin(self, rec: Any) -> None:
        pass

    async def read_class_prior(self, key: Any) -> list:
        return []

    async def record_shift_event(self, row: Any) -> None:
        pass

    async def read_shift_events(self, session_id: Any) -> list:
        return []

    async def reset_fingerprint(self, fp: EngineFingerprint) -> ResetCounts:
        self.reset_calls.append(fp)
        return self._reset_result

    # v2 surfaces — minimal no-op stubs so hydrate_for_session/flush work.
    async def list_fingerprints_for_class_key(
        self, *, candidate_fingerprints: Any, min_total_samples: int
    ) -> list:
        return []

    async def upsert_transmission_mode(self, rec: Any) -> None:
        pass

    async def read_transmission_mode(self, fp: EngineFingerprint) -> Any:
        return None

    async def delete_transmission_mode(self, fp: EngineFingerprint) -> int:
        return 0


def _make_predictor(
    *,
    config: AppConfig | None = None,
    repo: StubRepo | None = None,
    curve_resolver: StubCurveResolver | None = None,
    class_prior: StubClassPrior | None = None,
    change_point: StubChangePoint | None = None,
    shift_listener: StubShiftListener | None = None,
    bin_trainer: BinTrainer | None = None,
    ratio_kalman: RatioKalman | None = None,
) -> tuple[
    ShiftPredictor, StubCurveResolver, StubClassPrior, StubChangePoint, StubShiftListener, StubRepo
]:
    cfg = config or _make_config()
    repo_ = repo or StubRepo()
    resolver = curve_resolver or StubCurveResolver()
    prior = class_prior or StubClassPrior()
    cp = change_point or StubChangePoint()
    listener = shift_listener or StubShiftListener()
    trainer = bin_trainer or BinTrainer(half_life_samples=cfg.shift_ewma_half_life_samples)
    kalman = ratio_kalman or RatioKalman()

    predictor = ShiftPredictor(
        config=cfg,
        repo=repo_,
        bin_trainer=trainer,
        ratio_kalman=kalman,
        curve_resolver=resolver,
        class_prior=prior,
        change_point=cp,
        shift_listener=listener,
        transmission_mode_inferer=TransmissionModeInferer(config=cfg),
    )
    return predictor, resolver, prior, cp, listener, repo_


# ---------------------------------------------------------------------------
# Test 1: Fallback path — incomplete fingerprint
# ---------------------------------------------------------------------------


async def test_fallback_incomplete_fingerprint_returns_fallback_decoration() -> None:
    """Frame with carOrdinal=None -> stage='fallback', correct fallback target, no resolver call."""
    predictor, resolver, *_ = _make_predictor()

    raw = _make_frame_raw(car_ordinal=None, max_rpm=8000.0)
    frame = _make_frame(raw)

    deco = await predictor.on_frame(frame, session_uptime_s=120.0, session_type="race")

    assert deco.stage == "fallback"
    # fallback target = round(0.875 * 8000 / 100) * 100 = round(70) * 100 = 7000
    expected_target = round(0.875 * 8000.0 / 100) * 100
    assert deco.current_gear_target == expected_target
    assert deco.current_gear_confidence == 0.0
    assert deco.display_active is False
    # No resolver call for incomplete fingerprint
    assert len(resolver.calls) == 0


# ---------------------------------------------------------------------------
# Test 2: Eligible frame triggers training
# ---------------------------------------------------------------------------


class RecordingBinTrainer(BinTrainer):
    """BinTrainer subclass that records update calls."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.update_calls: list[tuple[Any, ...]] = []

    def update(  # type: ignore[override]
        self, fp: Any, gear: int, rpm: float, torque_nm: float, boost_psi: float, at: Any
    ) -> None:
        self.update_calls.append((fp, gear, rpm, torque_nm, boost_psi, at))
        super().update(fp, gear, rpm, torque_nm, boost_psi, at)


class RecordingRatioKalman(RatioKalman):
    """RatioKalman subclass that records update calls."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.update_calls: list[tuple[Any, ...]] = []

    def update(self, fp: Any, gear: int, ratio_measurement: float) -> None:  # type: ignore[override]
        self.update_calls.append((fp, gear, ratio_measurement))
        super().update(fp, gear, ratio_measurement)


async def test_eligible_frame_triggers_bin_trainer_and_ratio_kalman() -> None:
    """One eligible frame calls bin_trainer.update and ratio_kalman.update once each."""
    cfg = _make_config(shift_warmup_seconds=0)
    bin_trainer = RecordingBinTrainer(half_life_samples=cfg.shift_ewma_half_life_samples)
    ratio_kalman = RecordingRatioKalman()

    predictor, *_ = _make_predictor(
        config=cfg,
        bin_trainer=bin_trainer,
        ratio_kalman=ratio_kalman,
    )

    # Make a frame that looks like a stable gear for shift_gear_stable_frames=5 frames
    # We prime the predictor by sending eligible frames to fill the gear ring
    for _ in range(6):
        frame = _make_eligible_frame(gear=3, rpm=6500.0)
        await predictor.on_frame(frame, session_uptime_s=120.0, session_type="race")

    # After warming up, the last frame should have called bin_trainer
    assert len(bin_trainer.update_calls) >= 1
    assert len(ratio_kalman.update_calls) >= 1

    # All calls were for gear=3
    for call in bin_trainer.update_calls:
        assert call[1] == 3  # gear
        assert call[0] == _FP_COMPLETE  # fingerprint


# ---------------------------------------------------------------------------
# Test 3: Curve resolver invoked only every N samples
# ---------------------------------------------------------------------------


async def test_curve_resolver_invoked_every_n_samples() -> None:
    """With shift_recompute_every_n=10, feeding 25 eligible frames triggers resolve 3x."""
    cfg = _make_config(
        shift_recompute_every_n=10,
        shift_warmup_seconds=0,
        shift_gear_stable_frames=1,  # only need 1 frame for stability
    )
    predictor, resolver, *_ = _make_predictor(config=cfg)

    # Feed 25 eligible frames — first call triggers resolve immediately (no cache),
    # then every 10 thereafter: frame 1, frame 11, frame 21 = 3 total calls
    for i in range(25):
        frame = _make_eligible_frame(gear=3, rpm=6500.0)
        await predictor.on_frame(frame, session_uptime_s=120.0, session_type="race")

    assert len(resolver.calls) == 3


# ---------------------------------------------------------------------------
# Test 4: Ineligible frame echoes last decoration but updates ring buffers
# ---------------------------------------------------------------------------


async def test_ineligible_frame_echoes_last_decoration() -> None:
    """After an eligible frame establishes a recommendation, ineligible echoes it."""
    cfg = _make_config(
        shift_recompute_every_n=1,
        shift_warmup_seconds=0,
        shift_gear_stable_frames=1,
    )
    predictor, *_ = _make_predictor(config=cfg)

    # Eligible frame establishes a recommendation
    eligible = _make_eligible_frame(gear=3, rpm=6500.0)
    deco1 = await predictor.on_frame(eligible, session_uptime_s=120.0, session_type="race")
    assert deco1.by_gear  # must have some entries

    # Now send a low-throttle ineligible frame (gear=3 same) — echoes same byGear
    ineligible_raw = _make_frame_raw(
        gear=3,
        throttle=0.30,  # below both shift_throttle_min and shift_display_throttle_min
        is_race_on=True,
    )
    ineligible = _make_frame(ineligible_raw)
    deco2 = await predictor.on_frame(ineligible, session_uptime_s=120.0, session_type="race")

    # Same byGear map
    assert deco2.by_gear == deco1.by_gear
    # display_active is False because throttle < display_throttle_min
    assert deco2.display_active is False


# ---------------------------------------------------------------------------
# Test 5: display_active gates (FR-020)
# ---------------------------------------------------------------------------


async def test_display_active_false_for_drift_session() -> None:
    """Drift session: display_active=False even on eligible frame."""
    cfg = _make_config(
        shift_recompute_every_n=1, shift_warmup_seconds=0, shift_gear_stable_frames=1
    )
    predictor, *_ = _make_predictor(config=cfg)

    frame = _make_eligible_frame(gear=3)
    deco = await predictor.on_frame(frame, session_uptime_s=120.0, session_type="drift")

    assert deco.display_active is False


async def test_display_active_false_for_low_throttle() -> None:
    """throttle=0.5 (< display_throttle_min=0.70): display_active=False."""
    cfg = _make_config(
        shift_recompute_every_n=1,
        shift_warmup_seconds=0,
        shift_gear_stable_frames=1,
        shift_display_throttle_min=0.70,
    )
    predictor, *_ = _make_predictor(config=cfg)

    # First get a recommendation established with full throttle
    eligible = _make_eligible_frame(gear=3)
    await predictor.on_frame(eligible, session_uptime_s=120.0, session_type="race")

    # Then low-throttle
    raw = _make_frame_raw(gear=3, throttle=0.50, is_race_on=True)
    frame = _make_frame(raw)
    deco = await predictor.on_frame(frame, session_uptime_s=120.0, session_type="race")

    assert deco.display_active is False


async def test_display_active_false_for_fallback_stage() -> None:
    """stage='fallback': display_active=False (from incomplete fingerprint)."""
    predictor, *_ = _make_predictor()

    raw = _make_frame_raw(car_ordinal=None)
    frame = _make_frame(raw)
    deco = await predictor.on_frame(frame, session_uptime_s=120.0, session_type="race")

    assert deco.stage == "fallback"
    assert deco.display_active is False


async def test_display_active_true_when_all_gates_clear() -> None:
    """All gates clear (race, full throttle, learned stage): display_active=True."""
    cfg = _make_config(
        shift_recompute_every_n=1,
        shift_warmup_seconds=0,
        shift_gear_stable_frames=1,
        shift_display_throttle_min=0.70,
    )
    resolver = StubCurveResolver(
        returns=ResolvedCurves(
            optimal_rpm_by_gear={3: 7100},
            confidence_by_gear={3: 0.8},
            stage="learned",
            samples_by_gear_pair={(3, 4): 50},
        )
    )
    predictor, *_ = _make_predictor(config=cfg, curve_resolver=resolver)

    # eligible frame with throttle well above display_throttle_min
    frame = _make_eligible_frame(gear=3)
    deco = await predictor.on_frame(frame, session_uptime_s=120.0, session_type="race")

    assert deco.stage == "learned"
    assert deco.display_active is True


# ---------------------------------------------------------------------------
# Test 6: Change-point pause stops training
# ---------------------------------------------------------------------------


async def test_changepoint_pause_stops_bin_training() -> None:
    """When change_point.is_paused returns True, bin_trainer.update is NOT called."""
    cfg = _make_config(
        shift_recompute_every_n=1,
        shift_warmup_seconds=0,
        shift_gear_stable_frames=1,
    )
    bin_trainer = RecordingBinTrainer(half_life_samples=cfg.shift_ewma_half_life_samples)
    cp = StubChangePoint(paused=True)
    predictor, resolver, *_ = _make_predictor(
        config=cfg,
        bin_trainer=bin_trainer,
        change_point=cp,
    )

    for _ in range(5):
        frame = _make_eligible_frame(gear=3)
        await predictor.on_frame(frame, session_uptime_s=120.0, session_type="race")

    # bin_trainer should NOT have been called since paused
    assert len(bin_trainer.update_calls) == 0

    # But decorations should still be emitted (resolver still called with cached state)
    frame = _make_eligible_frame(gear=3)
    deco = await predictor.on_frame(frame, session_uptime_s=120.0, session_type="race")
    assert deco is not None


# ---------------------------------------------------------------------------
# Test 7: Shift event detection
# ---------------------------------------------------------------------------


async def test_shift_event_detected_on_gear_change() -> None:
    """Gear=3 then gear=4 on same fp -> shift_listener.on_shift called once
    after enough post-shift frames have accumulated (pending-shift queue)."""
    cfg = _make_config(
        shift_warmup_seconds=0,
        shift_gear_stable_frames=1,
        shift_recompute_every_n=1,
    )
    listener = StubShiftListener()
    predictor, *_ = _make_predictor(config=cfg, shift_listener=listener)

    # Frame in gear 3
    frame_g3 = _make_eligible_frame(gear=3, rpm=7000.0)
    await predictor.on_frame(frame_g3, session_uptime_s=120.0, session_type="race")

    # Frame in gear 4 — enqueues a PendingShift; listener has NOT fired yet.
    frame_g4 = _make_eligible_frame(gear=4, rpm=5500.0)
    await predictor.on_frame(frame_g4, session_uptime_s=120.0, session_type="race")
    assert listener.calls == [], "listener should defer firing until post_window has accumulated"

    # Drive 20 more post-shift frames to fill the post_window.
    for _ in range(20):
        await predictor.on_frame(
            _make_eligible_frame(gear=4, rpm=5500.0),
            session_uptime_s=120.0,
            session_type="race",
        )

    # Shift listener should have been notified.
    assert len(listener.calls) >= 1
    call = listener.calls[0]
    assert call["gear_from"] == 3
    assert call["gear_to"] == 4


# ---------------------------------------------------------------------------
# Test 8: hydrate_for_session reads and hydrates
# ---------------------------------------------------------------------------


async def test_hydrate_for_session_loads_bins_and_ratios() -> None:
    """hydrate_for_session reads from repo and calls bin_trainer.hydrate + ratio_kalman.hydrate."""
    cfg = _make_config()

    repo = StubRepo()
    now = datetime.now(tz=UTC)
    repo.bins = [
        BinRecord(
            fingerprint=_FP_COMPLETE,
            gear=3,
            rpm_bin=65,
            count=100,
            mean_torque_nm=400.0,
            m2_torque=2000.0,
            q90_torque_nm=420.0,
            mean_boost_psi=0.0,
            last_updated=now,
        )
    ]
    repo.ratios = [
        RatioRecord(
            fingerprint=_FP_COMPLETE,
            gear=3,
            ratio=217.5,
            variance=0.02,
            last_updated=now,
        )
    ]

    bin_trainer = RecordingBinTrainer(half_life_samples=cfg.shift_ewma_half_life_samples)
    kalman = RecordingRatioKalman()
    predictor, *_ = _make_predictor(
        config=cfg, repo=repo, bin_trainer=bin_trainer, ratio_kalman=kalman
    )

    await predictor.hydrate_for_session(_SESSION, _FP_COMPLETE)

    # After hydrate, bin_trainer should have the bin data accessible
    snap = bin_trainer.snapshot(_FP_COMPLETE)
    assert (3, 65) in snap
    assert snap[(3, 65)].count == pytest.approx(100.0, rel=1e-3)

    # Ratio state should have been loaded
    reading = kalman.read(_FP_COMPLETE, 3)
    assert reading is not None
    assert reading.ratio == pytest.approx(217.5, rel=1e-3)


# ---------------------------------------------------------------------------
# Test 9: flush() calls both bin_trainer.flush and ratio_kalman.flush
# ---------------------------------------------------------------------------


async def test_flush_calls_both_trainers() -> None:
    """flush() persists via both bin_trainer.flush(repo) and ratio_kalman.flush(repo)."""
    cfg = _make_config(
        shift_recompute_every_n=1,
        shift_warmup_seconds=0,
        shift_gear_stable_frames=1,
    )
    repo = StubRepo()
    predictor, *_ = _make_predictor(config=cfg, repo=repo)

    # Feed one eligible frame to create some state
    frame = _make_eligible_frame(gear=3)
    await predictor.on_frame(frame, session_uptime_s=120.0, session_type="race")

    await predictor.flush()

    # upsert_bins should have been called (from bin_trainer.flush)
    assert len(repo.upsert_bins_calls) >= 1
    # upsert_ratio should have been called (from ratio_kalman.flush)
    assert len(repo.upsert_ratio_calls) >= 1


# ---------------------------------------------------------------------------
# Test 10: reset(fp) calls repo.reset_fingerprint and returns ResetCounts
# ---------------------------------------------------------------------------


async def test_reset_calls_repo_and_returns_counts() -> None:
    """reset(fp) calls repo.reset_fingerprint and returns its ResetCounts."""
    repo = StubRepo()
    predictor, *_ = _make_predictor(repo=repo)

    result = await predictor.reset(_FP_COMPLETE)

    assert _FP_COMPLETE in repo.reset_calls
    assert isinstance(result, ResetCounts)
    assert result.engine_curves == 3
    assert result.gear_ratios == 2
    assert result.shift_events == 1


# ---------------------------------------------------------------------------
# Test 11: to_wire() shape matches FR-018 spec
# ---------------------------------------------------------------------------


def test_to_wire_shape_matches_fr018() -> None:
    """ShiftFrameDecoration.to_wire() returns the exact FR-018 camelCase keys."""
    deco = ShiftFrameDecoration(
        by_gear={3: 7200, 4: 7100},
        confidence_by_gear={3: 0.78, 4: 0.70},
        current_gear_target=7100,
        current_gear_confidence=0.78,
        display_active=True,
        stage="learned",
        by_gear_samples={3: 187, 4: 100},
        fingerprint={"carOrdinal": 2451, "performanceIndex": 812, "numCylinders": 6},
    )

    wire = deco.to_wire()

    # Check exact keys
    assert "byGear" in wire
    assert "confidenceByGear" in wire
    assert "currentGearTarget" in wire
    assert "currentGearConfidence" in wire
    assert "displayActive" in wire
    assert "stage" in wire
    assert "byGearSamples" in wire
    assert "fingerprint" in wire
    assert "modelVersion" in wire

    # Check values
    assert wire["byGear"] == {"3": 7200, "4": 7100}
    assert wire["confidenceByGear"] == {"3": 0.78, "4": 0.70}
    assert wire["currentGearTarget"] == 7100
    assert wire["currentGearConfidence"] == 0.78
    assert wire["displayActive"] is True
    assert wire["stage"] == "learned"
    assert wire["byGearSamples"] == {"3": 187, "4": 100}
    assert wire["fingerprint"]["carOrdinal"] == 2451
    assert wire["modelVersion"] == "shift-v1"

    # Keys must be str for JSON (byGear, confidenceByGear, byGearSamples)
    for k in wire["byGear"]:
        assert isinstance(k, str)
    for k in wire["confidenceByGear"]:
        assert isinstance(k, str)
    for k in wire["byGearSamples"]:
        assert isinstance(k, str)
