"""Unit tests for ShiftPredictor + TransmissionModeInferer wiring (FR-042, FR-043).

Four scenarios:
1. After 12 clean upshifts driven via ``on_shift_event``, the next frame's
   ``ShiftFrameDecoration.transmission_mode`` block reports ``mode="manual"``
   with non-zero confidence (high-stdev RPM samples).
2. Once the in-memory confidence is non-zero (≥ classification threshold), the
   repo's ``upsert_transmission_mode`` has been called and ``read_transmission_mode``
   returns a persisted row.
3. Persistence cadence: ``upsert_transmission_mode`` is only re-called when
   confidence jumps by ≥ 0.1 OR when the mode classification changes. After
   crossing the initial classification threshold (one persist) and continuing
   to accumulate samples (confidence increments by ≥ 0.1), exactly one
   additional persist occurs — not one per shift event.
4. ``flush()`` unconditionally persists the latest in-memory state for each
   touched fingerprint, even if no confidence increment has occurred since
   the last persist.
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
    TransmissionModeBlock,
)
from fh6.application.services.shift.transmission_mode import TransmissionModeInferer
from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.domain.ports.shift_predictor_repo import TransmissionModeRecord
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
_SESSION = SessionId("test-session-trans-mode")
_CAR = CarId("car-trans-mode")


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


def _frame(*, slip: float = 0.05) -> DecodedFrame:
    """A frame that passes FR-003 driver/session preconditions, plus a fingerprint
    matching _FP. Used to coax the predictor into emitting a decoration we can
    inspect for the transmission_mode block.
    """
    raw = FrameRaw(
        is_race_on=True,
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
    def resolve(self, bins: Any, ratios: Any, idle_rpm: float, max_rpm: float) -> ResolvedCurves:
        return ResolvedCurves(
            optimal_rpm_by_gear={3: 7100},
            confidence_by_gear={3: 0.8},
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


class _CountingRepo(InMemoryShiftPredictorRepo):
    """Adds a call-count on upsert_transmission_mode so tests can assert
    persistence cadence.
    """

    def __init__(self) -> None:
        super().__init__()
        self.upsert_trans_mode_calls: list[TransmissionModeRecord] = []

    async def upsert_transmission_mode(self, rec: TransmissionModeRecord) -> None:
        self.upsert_trans_mode_calls.append(rec)
        await super().upsert_transmission_mode(rec)


def _make_predictor(
    cfg: AppConfig | None = None, repo: InMemoryShiftPredictorRepo | None = None
) -> ShiftPredictor:
    cfg = cfg or _make_config()
    repo = repo or InMemoryShiftPredictorRepo()
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


_MANUAL_RPMS = [
    5500.0,
    6200.0,
    5800.0,
    6800.0,
    6100.0,
    6500.0,
    5400.0,
    6900.0,
    6000.0,
    5700.0,
    6400.0,
    6300.0,
]


@pytest.mark.asyncio
async def test_decoration_carries_transmission_mode_block_after_clean_upshifts() -> None:
    """Drive 12 clean upshifts at gear pair (3,4) with manual-pattern RPMs.
    The next frame's decoration carries a non-default transmission_mode block.
    """
    predictor = _make_predictor()

    for rpm in _MANUAL_RPMS:
        await predictor.on_shift_event(
            fp=_FP,
            gear_from=3,
            gear_to=4,
            pre_shift_rpm=rpm,
            is_clean_upshift=True,
        )

    decoration = await predictor.on_frame(_frame(), session_uptime_s=120.0, session_type="race")
    block = decoration.transmission_mode
    assert isinstance(block, TransmissionModeBlock)
    assert block.mode == "manual"
    assert block.confidence > 0.0

    # Wire round-trip: camelCase ``transmissionMode`` key, always present.
    wire = decoration.to_wire()
    assert wire["transmissionMode"] == {
        "mode": "manual",
        "confidence": block.confidence,
    }


@pytest.mark.asyncio
async def test_persisted_after_classification_threshold() -> None:
    """After classification crosses confidence ≥ 0.5 (i.e. once a mode != "unknown"
    is reached), the repo holds a transmission-mode row for the fingerprint.
    """
    repo = InMemoryShiftPredictorRepo()
    predictor = _make_predictor(repo=repo)

    # 12 samples > min_samples (10) → classification is non-"unknown".
    for rpm in _MANUAL_RPMS:
        await predictor.on_shift_event(
            fp=_FP,
            gear_from=3,
            gear_to=4,
            pre_shift_rpm=rpm,
            is_clean_upshift=True,
        )

    persisted = await repo.read_transmission_mode(_FP)
    assert persisted is not None
    assert persisted.mode == "manual"
    assert persisted.confidence > 0.0
    # The 10th sample triggers the initial persist (mode_changed unknown→manual).
    # Samples 11 + 12 nudge confidence by 0.033 / 0.067 — both below the 0.1
    # milestone, so no further persists occur until ``flush()``.
    assert persisted.sample_count == 10


@pytest.mark.asyncio
async def test_persistence_cadence_increments_by_tenth() -> None:
    """Drive enough samples to cross the initial classification (one persist
    expected), then continue driving samples through to push confidence up by
    ≥ 0.1 (one more persist expected). Total persists: exactly 2, not 12+.
    """
    repo = _CountingRepo()
    predictor = _make_predictor(repo=repo)

    # First 10 samples — at the 10th the inferer transitions from "unknown" to
    # "manual" and the predictor persists once (mode_changed=True).
    for rpm in _MANUAL_RPMS[:10]:
        await predictor.on_shift_event(
            fp=_FP,
            gear_from=3,
            gear_to=4,
            pre_shift_rpm=rpm,
            is_clean_upshift=True,
        )
    assert len(repo.upsert_trans_mode_calls) == 1
    first_conf = repo.upsert_trans_mode_calls[-1].confidence
    # 10 samples → confidence = 10/30 ≈ 0.333.
    assert first_conf == pytest.approx(10 / 30, abs=1e-6)

    # Sample 11: confidence rises to 11/30 ≈ 0.367 — delta 0.033 < 0.1, no persist.
    await predictor.on_shift_event(
        fp=_FP,
        gear_from=3,
        gear_to=4,
        pre_shift_rpm=_MANUAL_RPMS[10],
        is_clean_upshift=True,
    )
    assert len(repo.upsert_trans_mode_calls) == 1, (
        "increment 11/30 - 10/30 ≈ 0.033 < 0.1, no persist expected"
    )

    # Continue accumulating until confidence steps up by ≥ 0.1 from 0.333.
    # Need at least 14 total samples for 14/30 - 10/30 = 0.133 ≥ 0.1.
    extra_rpms = [6050.0, 5950.0, 6150.0, 5850.0]  # samples 12, 13, 14, 15
    for rpm in extra_rpms:
        await predictor.on_shift_event(
            fp=_FP,
            gear_from=3,
            gear_to=4,
            pre_shift_rpm=rpm,
            is_clean_upshift=True,
        )

    assert len(repo.upsert_trans_mode_calls) == 2, (
        f"expected exactly 2 persists (one per 0.1 increment milestone), got "
        f"{len(repo.upsert_trans_mode_calls)}"
    )
    second_conf = repo.upsert_trans_mode_calls[-1].confidence
    assert second_conf - first_conf >= 0.1


@pytest.mark.asyncio
async def test_flush_persists_latest_state_unconditionally() -> None:
    """``flush()`` persists the current in-memory state for each touched
    fingerprint even when no 0.1-confidence milestone has elapsed since the
    last persist.
    """
    repo = _CountingRepo()
    predictor = _make_predictor(repo=repo)

    # Drive exactly 10 samples → one persist (mode_changed unknown→manual).
    for rpm in _MANUAL_RPMS[:10]:
        await predictor.on_shift_event(
            fp=_FP,
            gear_from=3,
            gear_to=4,
            pre_shift_rpm=rpm,
            is_clean_upshift=True,
        )
    assert len(repo.upsert_trans_mode_calls) == 1

    # One more sample — increment too small for a normal persist.
    await predictor.on_shift_event(
        fp=_FP,
        gear_from=3,
        gear_to=4,
        pre_shift_rpm=_MANUAL_RPMS[10],
        is_clean_upshift=True,
    )
    assert len(repo.upsert_trans_mode_calls) == 1

    # Flush — unconditional persist.
    await predictor.flush()
    assert len(repo.upsert_trans_mode_calls) == 2
    final = repo.upsert_trans_mode_calls[-1]
    assert final.sample_count == 11
    assert final.mode == "manual"


@pytest.mark.asyncio
async def test_non_clean_upshift_is_ignored() -> None:
    """An ``on_shift_event`` call with ``is_clean_upshift=False`` does NOT
    forward to the inferer, so no samples accumulate and no persist occurs.
    """
    repo = _CountingRepo()
    predictor = _make_predictor(repo=repo)

    for rpm in _MANUAL_RPMS:
        await predictor.on_shift_event(
            fp=_FP,
            gear_from=3,
            gear_to=4,
            pre_shift_rpm=rpm,
            is_clean_upshift=False,
        )

    assert repo.upsert_trans_mode_calls == []
    decoration = await predictor.on_frame(_frame(), session_uptime_s=120.0, session_type="race")
    # No samples → inferer reports "unknown" with zero confidence — but the
    # block is still always present on the wire.
    assert decoration.transmission_mode.mode == "unknown"
    assert decoration.transmission_mode.confidence == 0.0


@pytest.mark.asyncio
async def test_hydrate_for_session_seeds_persisted_block() -> None:
    """After ``hydrate_for_session`` reads a persisted transmission-mode row,
    subsequent decorations report that mode/confidence even before any new
    samples arrive in the live session.
    """
    repo = InMemoryShiftPredictorRepo()
    # Pre-seed a persisted row directly through the repo.
    await repo.upsert_transmission_mode(
        TransmissionModeRecord(
            fingerprint=_FP,
            mode="auto",
            confidence=0.7,
            sample_count=21,
            last_updated=_NOW,
        )
    )
    predictor = _make_predictor(repo=repo)
    await predictor.hydrate_for_session(_SESSION, _FP)

    decoration = await predictor.on_frame(_frame(), session_uptime_s=120.0, session_type="race")
    assert decoration.transmission_mode.mode == "auto"
    assert decoration.transmission_mode.confidence == pytest.approx(0.7)
