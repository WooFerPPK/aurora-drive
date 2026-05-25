"""Unit tests for ShiftPredictor downshift cache + wire decoration (FR-046, FR-047, FR-049).

Five scenarios:

1. With fully-hydrated curves across gears 2-5, the decoration carries
   ``by_gear_downshift`` populated for gears 3, 4, 5 (gear 2 unviable in this
   fixture, gear 1 explicitly absent).
2. ``current_gear_downshift_target == by_gear_downshift[str(current_gear)]``
   when present; ``None`` when absent (e.g. current gear 2).
3. When ``current_gear == 1``, ``current_gear_downshift_target is None``.
4. When the 3->2 pair is unviable (resolver returns no key for gear 3),
   ``by_gear_downshift["3"]`` is absent from the wire.
5. ``display_active_down`` flips based on brake/throttle per FR-049.
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
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint
from fh6.domain.value_objects.ids import CarId, SessionId
from fh6.infrastructure.config import AppConfig
from tests.contract.fake_repos import InMemoryShiftPredictorRepo

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_FP = EngineFingerprint(car_ordinal=2451, performance_index=812, num_cylinders=6)
_NOW = datetime(2026, 5, 23, 10, 0, 0, tzinfo=UTC)
_SESSION = SessionId("test-session-downshift")
_CAR = CarId("car-downshift")


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
        shift_recompute_every_n=1,
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


def _make_frame(
    *,
    gear: int = 3,
    rpm: float = 6500.0,
    throttle: float = 0.99,
    brake: float = 0.0,
    is_race_on: bool = True,
) -> DecodedFrame:
    """Build an eligible-by-default frame matching _FP."""
    raw = FrameRaw(
        is_race_on=is_race_on,
        timestamp_ms=1_000_000,
        engine={
            "currentRpm": rpm,
            "rpm": rpm,
            "maxRpm": 8000.0,
            "idleRpm": 900.0,
            "torque": 400.0,
            "torque_nm": 400.0,
            "boost": 0.0,
            "boost_psi": 0.0,
        },
        drivetrain={"gear": gear, "clutch": 0.0},
        motion={"speed": 40.0},
        inputs={
            "throttle": throttle,
            "brake": brake,
            "clutch": 0.0,
            "steer": 0.05,
        },
        wheels={wn: {"combinedSlip": 0.05} for wn in ("fl", "fr", "rl", "rr")},
        world={
            "carOrdinal": _FP.car_ordinal,
            "performanceIndex": _FP.performance_index,
            "numCylinders": _FP.num_cylinders,
            "maxRpm": 8000.0,
        },
        race={},
        tail_reserved_byte=0,
    )
    return DecodedFrame(
        session_id=_SESSION,
        car_id=_CAR,
        received_at=_NOW,
        raw=raw,
    )


# ---------------------------------------------------------------------------
# Stub collaborators — return ResolvedCurves with crafted downshift fields
# ---------------------------------------------------------------------------

# Fully-hydrated curves: gears 2..5 fitted, gears 3,4,5 have viable downshift
# targets; gear 2 omitted (the 2->1 pair is unviable in this fixture).
_DEFAULT_CURVES_FULL = ResolvedCurves(
    optimal_rpm_by_gear={2: 7200, 3: 7100, 4: 7000, 5: 6900},
    confidence_by_gear={2: 0.7, 3: 0.8, 4: 0.7, 5: 0.65},
    stage="learned",
    samples_by_gear_pair={(2, 3): 250, (3, 4): 220, (4, 5): 200, (5, 6): 0},
    by_gear_downshift={3: 4800, 4: 5200, 5: 5400},
    confidence_by_gear_downshift={3: 0.62, 4: 0.71, 5: 0.55},
)

# "3->2 unviable" variant: gear 3 missing from by_gear_downshift.
_DEFAULT_CURVES_3_UNVIABLE = ResolvedCurves(
    optimal_rpm_by_gear={2: 7200, 3: 7100, 4: 7000, 5: 6900},
    confidence_by_gear={2: 0.7, 3: 0.8, 4: 0.7, 5: 0.65},
    stage="learned",
    samples_by_gear_pair={(2, 3): 250, (3, 4): 220, (4, 5): 200, (5, 6): 0},
    by_gear_downshift={4: 5200, 5: 5400},
    confidence_by_gear_downshift={4: 0.71, 5: 0.55},
)


class _StubCurveResolver:
    def __init__(self, returns: ResolvedCurves) -> None:
        self._returns = returns

    def resolve(self, bins: Any, ratios: Any, idle_rpm: float, max_rpm: float) -> ResolvedCurves:
        return self._returns


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


def _make_predictor(
    *,
    cfg: AppConfig | None = None,
    curves: ResolvedCurves | None = None,
) -> ShiftPredictor:
    cfg = cfg or _make_config()
    curves = curves or _DEFAULT_CURVES_FULL
    return ShiftPredictor(
        config=cfg,
        repo=InMemoryShiftPredictorRepo(),
        bin_trainer=BinTrainer(half_life_samples=cfg.shift_ewma_half_life_samples),
        ratio_kalman=RatioKalman(),
        curve_resolver=_StubCurveResolver(curves),
        class_prior=_StubClassPrior(),
        change_point=_StubChangePoint(),
        shift_listener=_StubShiftListener(),
        transmission_mode_inferer=TransmissionModeInferer(config=cfg),
    )


# ---------------------------------------------------------------------------
# Test 1: by_gear_downshift populated for hydrated gears
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decoration_carries_by_gear_downshift_for_hydrated_gears() -> None:
    predictor = _make_predictor()

    # Drive one eligible frame at gear 3 — triggers a curve resolve.
    decoration = await predictor.on_frame(
        _make_frame(gear=3, rpm=6500.0, throttle=0.99),
        session_uptime_s=120.0,
        session_type="race",
    )

    # by_gear_downshift carries entries for gears 3, 4, 5.
    assert decoration.by_gear_downshift == {3: 4800, 4: 5200, 5: 5400}
    # Gear 1 explicitly absent (cannot downshift further).
    assert 1 not in decoration.by_gear_downshift
    # Confidence map mirrors the keys.
    assert decoration.confidence_by_gear_downshift == {
        3: 0.62,
        4: 0.71,
        5: 0.55,
    }

    # Wire round-trip: camelCase keys, string keys for gear maps.
    wire = decoration.to_wire()
    assert wire["byGearDownshift"] == {"3": 4800, "4": 5200, "5": 5400}
    assert wire["confidenceByGearDownshift"] == {
        "3": 0.62,
        "4": 0.71,
        "5": 0.55,
    }


# ---------------------------------------------------------------------------
# Test 2: current_gear_downshift_target tracks by_gear_downshift[current_gear]
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_current_gear_downshift_target_matches_by_gear_or_none() -> None:
    predictor = _make_predictor()

    # current_gear=3 → target=4800.
    deco_g3 = await predictor.on_frame(
        _make_frame(gear=3, rpm=6500.0, throttle=0.99),
        session_uptime_s=120.0,
        session_type="race",
    )
    assert deco_g3.current_gear_downshift_target == 4800
    assert deco_g3.current_gear_downshift_confidence == pytest.approx(0.62)
    assert deco_g3.to_wire()["currentGearDownshiftTarget"] == 4800
    assert deco_g3.to_wire()["currentGearDownshiftConfidence"] == pytest.approx(0.62)

    # current_gear=2 (key absent from by_gear_downshift) → target=None, confidence=0.
    deco_g2 = await predictor.on_frame(
        _make_frame(gear=2, rpm=5500.0, throttle=0.99),
        session_uptime_s=120.0,
        session_type="race",
    )
    assert deco_g2.current_gear_downshift_target is None
    assert deco_g2.current_gear_downshift_confidence == 0.0
    assert deco_g2.to_wire()["currentGearDownshiftTarget"] is None


# ---------------------------------------------------------------------------
# Test 3: current_gear == 1 → target is None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_current_gear_one_yields_none_target() -> None:
    predictor = _make_predictor()

    deco = await predictor.on_frame(
        _make_frame(gear=1, rpm=4500.0, throttle=0.99),
        session_uptime_s=120.0,
        session_type="race",
    )
    assert deco.current_gear_downshift_target is None
    assert deco.current_gear_downshift_confidence == 0.0


# ---------------------------------------------------------------------------
# Test 4: 3->2 unviable → byGearDownshift omits "3"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unviable_pair_omits_key_from_wire() -> None:
    predictor = _make_predictor(curves=_DEFAULT_CURVES_3_UNVIABLE)

    deco = await predictor.on_frame(
        _make_frame(gear=3, rpm=6500.0, throttle=0.99),
        session_uptime_s=120.0,
        session_type="race",
    )

    # The 3->2 pair is unviable: key 3 absent from by_gear_downshift.
    assert 3 not in deco.by_gear_downshift
    # Other gears still present.
    assert deco.by_gear_downshift == {4: 5200, 5: 5400}
    # Wire mirrors this (no "3" key).
    wire = deco.to_wire()
    assert "3" not in wire["byGearDownshift"]
    assert wire["byGearDownshift"] == {"4": 5200, "5": 5400}
    # current_gear=3 has no target.
    assert deco.current_gear_downshift_target is None


# ---------------------------------------------------------------------------
# Test 5: display_active_down flips with brake/throttle per FR-049
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_display_active_down_flips_with_brake_and_throttle() -> None:
    """FR-049: display_active_down is True iff:
      - transmissionMode.mode != "auto"
      - session_type != "drift"
      - currentGearDownshiftTarget is not None
      - stage != "fallback"
      - brake >= shift_downshift_brake_display_min (0.10)
        OR throttle < shift_downshift_throttle_display_max (0.30)

    The transmission_mode inferer in this test starts at "unknown" — that
    satisfies the "mode != auto" clause (unknown also shows the marker).
    """
    predictor = _make_predictor()

    # Case A: WOT, no brake — throttle (0.99) is NOT < 0.30, brake (0.0)
    #         is NOT >= 0.10 → display_active_down=False.
    deco_wot = await predictor.on_frame(
        _make_frame(gear=3, rpm=6500.0, throttle=0.99, brake=0.0),
        session_uptime_s=120.0,
        session_type="race",
    )
    assert deco_wot.display_active_down is False
    assert deco_wot.to_wire()["displayActiveDown"] is False

    # Case B: Brake on, off-throttle (corner-approach pattern).
    # The frame is ineligible for training (brake > shift_brake_max) but
    # the decoration is still emitted from the cached curves. brake=0.50
    # >= 0.10 → display_active_down=True.
    deco_brake = await predictor.on_frame(
        _make_frame(gear=3, rpm=6500.0, throttle=0.10, brake=0.50),
        session_uptime_s=120.0,
        session_type="race",
    )
    assert deco_brake.display_active_down is True
    assert deco_brake.to_wire()["displayActiveDown"] is True

    # Case C: drift session always suppresses the marker, even with brake on.
    deco_drift = await predictor.on_frame(
        _make_frame(gear=3, rpm=6500.0, throttle=0.10, brake=0.50),
        session_uptime_s=120.0,
        session_type="drift",
    )
    assert deco_drift.display_active_down is False


# ---------------------------------------------------------------------------
# FR-011 drift penalty: decoration multiplies confidence by (1 - drift_penalty)
# ---------------------------------------------------------------------------


class _PausedChangePoint:
    """Stub ChangePointObserver whose ``is_paused`` flag is toggleable."""

    def __init__(self, paused: bool = False) -> None:
        self.paused = paused

    def observe(self, *args: Any, **kwargs: Any) -> None:
        return None

    def reset(self, fp: Any) -> None:
        return None

    def is_paused(self, fp: Any) -> bool:
        return self.paused


def _make_predictor_with_pauseable(
    *,
    cfg: AppConfig | None = None,
    curves: ResolvedCurves | None = None,
) -> tuple[ShiftPredictor, _PausedChangePoint]:
    """Builds a predictor with a toggleable change-point stub."""
    cfg = cfg or _make_config()
    curves = curves or _DEFAULT_CURVES_FULL
    cp = _PausedChangePoint(paused=False)
    predictor = ShiftPredictor(
        config=cfg,
        repo=InMemoryShiftPredictorRepo(),
        bin_trainer=BinTrainer(half_life_samples=cfg.shift_ewma_half_life_samples),
        ratio_kalman=RatioKalman(),
        curve_resolver=_StubCurveResolver(curves),
        class_prior=_StubClassPrior(),
        change_point=cp,
        shift_listener=_StubShiftListener(),
        transmission_mode_inferer=TransmissionModeInferer(config=cfg),
    )
    return predictor, cp


@pytest.mark.asyncio
async def test_fr011_drift_penalty_halves_confidence_when_paused() -> None:
    """When change_point.is_paused returns True for fp, the decoration's
    confidence is halved (drift_penalty=0.5). When paused returns False, the
    cached pre-drift confidence is used as-is.

    Both upshift and downshift confidence maps must reflect the penalty.
    """
    predictor, cp = _make_predictor_with_pauseable()

    # First frame with is_paused=False → full pre-drift confidence.
    cp.paused = False
    deco_normal = await predictor.on_frame(
        _make_frame(gear=3, rpm=6500.0, throttle=0.99),
        session_uptime_s=120.0,
        session_type="race",
    )
    assert deco_normal.current_gear_confidence == pytest.approx(0.8)
    assert deco_normal.current_gear_downshift_confidence == pytest.approx(0.62)
    assert deco_normal.confidence_by_gear[3] == pytest.approx(0.8)
    assert deco_normal.confidence_by_gear_downshift[3] == pytest.approx(0.62)

    # Flip paused on → drift_penalty=0.5 multiplies every confidence by 0.5.
    cp.paused = True
    deco_paused = await predictor.on_frame(
        _make_frame(gear=3, rpm=6500.0, throttle=0.99),
        session_uptime_s=120.0,
        session_type="race",
    )
    assert deco_paused.current_gear_confidence == pytest.approx(0.8 * 0.5)
    assert deco_paused.current_gear_downshift_confidence == pytest.approx(0.62 * 0.5)
    # Map values mirror.
    assert deco_paused.confidence_by_gear[3] == pytest.approx(0.8 * 0.5)
    assert deco_paused.confidence_by_gear[4] == pytest.approx(0.7 * 0.5)
    assert deco_paused.confidence_by_gear_downshift[3] == pytest.approx(0.62 * 0.5)
    assert deco_paused.confidence_by_gear_downshift[4] == pytest.approx(0.71 * 0.5)

    # Flip paused off again → confidence reverts to full pre-drift value.
    cp.paused = False
    deco_recovered = await predictor.on_frame(
        _make_frame(gear=3, rpm=6500.0, throttle=0.99),
        session_uptime_s=120.0,
        session_type="race",
    )
    assert deco_recovered.current_gear_confidence == pytest.approx(0.8)
    assert deco_recovered.current_gear_downshift_confidence == pytest.approx(0.62)


@pytest.mark.asyncio
async def test_fr011_cached_confidence_remains_pre_drift() -> None:
    """The cached ResolvedCurves.confidence_by_gear value stays pre-drift so
    that flipping the drift flag changes the decoration without forcing a
    curve recompute. This keeps the cache invariant across drift transitions.
    """
    predictor, cp = _make_predictor_with_pauseable()

    # Drive one frame with paused=False to populate the cache.
    cp.paused = False
    await predictor.on_frame(
        _make_frame(gear=3, rpm=6500.0, throttle=0.99),
        session_uptime_s=120.0,
        session_type="race",
    )

    fp = EngineFingerprint(
        car_ordinal=_FP.car_ordinal,
        performance_index=_FP.performance_index,
        num_cylinders=_FP.num_cylinders,
    )
    state = predictor._states[fp]
    assert state.cached_curves is not None
    # Pre-drift cache values match the stub's raw output.
    assert state.cached_curves.confidence_by_gear[3] == pytest.approx(0.8)
    assert state.cached_curves.confidence_by_gear_downshift[3] == pytest.approx(0.62)

    # Toggle paused. Cache should NOT have been updated.
    cp.paused = True
    deco = await predictor.on_frame(
        _make_frame(gear=3, rpm=6500.0, throttle=0.99),
        session_uptime_s=120.0,
        session_type="race",
    )
    # Decoration reflects the penalty.
    assert deco.confidence_by_gear[3] == pytest.approx(0.8 * 0.5)
    # But the cached curves remain pre-drift.
    assert state.cached_curves.confidence_by_gear[3] == pytest.approx(0.8)
    assert state.cached_curves.confidence_by_gear_downshift[3] == pytest.approx(0.62)
