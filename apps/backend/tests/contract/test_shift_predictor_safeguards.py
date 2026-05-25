"""Hard-guarantee safeguard tests for the shift predictor (Task 23 + Task 18).

These assert design invariants AS CODE, not as docs:

v1 safeguards:
- FR-017: ShiftEventEvaluator never calls upsert_bin / upsert_bins.
- FR-003: drift sessions never train.
- FR-020: displayActive is False at low throttle.
- FR-023: reset clears bins, ratios, and shift events.
- Stage transitions go fallback → prior/learned in order.

v2 safeguards (Task 18, extends v1):
- FR-017 carry-over: ShiftEventEvaluator's downshift branch also doesn't
  upsert_bin (the v1 grep covers the whole file; the new presence check
  asserts the downshift method exists so future refactors don't quietly
  delete it).
- FR-037 Signal A: WOT + combinedSlip >= tcs_slip_threshold rejects with
  reason="assist_intervention" and intervention_suspected=True.
- FR-037 Signal B: WOT + torque below class-prior ratio rejects with
  reason="assist_intervention" and intervention_suspected=True.
- FR-041 1→2 exclusion: TransmissionModeInferer ignores 1→2 samples in
  dispersion classification.
- FR-044 reset extension: reset deletes the transmission_modes row and
  reports the count in the response.
- FR-045 unviable downshift: solve_optimal(direction="down") returns None
  when ratio_post is large enough to put the pre-shift max below idle.
- FR-049 display gate: transmissionMode.mode == "auto" forces
  displayActiveDown to False even with an otherwise-viable downshift.
"""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fh6.application.services.shift.bin_trainer import BinTrainer
from fh6.application.services.shift.curve_resolver import ShiftCurveResolver
from fh6.application.services.shift.ratio_kalman import RatioKalman
from fh6.application.services.shift.shift_predictor import (
    ShiftPredictor,
    TransmissionModeBlock,
)
from fh6.application.services.shift.training_filter import (
    AssistCheckInputs,
    FilterInputs,
    check_frame,
)
from fh6.application.services.shift.transmission_mode import TransmissionModeInferer
from fh6.domain.entities.frame import DecodedFrame, FrameRaw
from fh6.domain.ports.shift_predictor_repo import (
    BinRecord,
    RatioRecord,
    ShiftEventRow,
    TransmissionModeRecord,
)
from fh6.domain.value_objects.engine_fingerprint import EngineFingerprint
from fh6.domain.value_objects.ids import CarId, SessionId
from tests.contract.fake_repos import InMemoryShiftPredictorRepo
from tests.unit.test_shift_event_evaluator import _make_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FP = EngineFingerprint(car_ordinal=2451, performance_index=812, num_cylinders=6)
SESSION_ID = SessionId("safeguard-session")


def _raw(*, gear: int = 4, rpm: float = 6500.0, throttle: float = 0.99) -> FrameRaw:
    return FrameRaw(
        is_race_on=True,
        timestamp_ms=1000,
        engine={
            "rpm": rpm,
            "idleRpm": 900.0,
            "maxRpm": 8000.0,
            "torque": 400.0,
            "currentRpm": rpm,
            "boost": 0.0,
        },
        drivetrain={"gear": gear, "clutch": 0.0, "type": "AWD"},
        motion={
            "speed_mps": 41.0,
            "velocity": {"x": 0.0, "y": 0.0, "z": 41.0},
            "acceleration": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        inputs={"throttle": throttle, "brake": 0.0, "clutch": 0.0, "steer": 0.0},
        wheels={
            wn: {"combinedSlip": 0.05, "surfaceRumble": 0.0, "onRumble": 0}
            for wn in ("fl", "fr", "rl", "rr")
        },
        world={
            "carOrdinal": FP.car_ordinal,
            "carClass": "A",
            "performanceIndex": FP.performance_index,
            "numCylinders": FP.num_cylinders,
            "carGroup": 18,
            "smashableVelDiff": 0.0,
            "smashableMass": 0.0,
        },
        race={"lap": 1, "currentLapS": 12.0, "raceTimeS": 60.0},
        tail_reserved_byte=0,
    )


def _frame(**raw_kw) -> DecodedFrame:
    return DecodedFrame(
        session_id=SESSION_ID,
        car_id=CarId("car-001"),
        received_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        raw=_raw(**raw_kw),
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


def _make_predictor(repo):
    cfg = _make_config(shift_warmup_seconds=1)
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


# ---------------------------------------------------------------------------
# FR-017: shift outcomes never train the curve
# ---------------------------------------------------------------------------


def test_shift_event_evaluator_does_not_call_upsert_bin() -> None:
    """Static grep: the evaluator must never invoke upsert_bin/upsert_bins.

    This is the *core* safeguard for FR-017. Any future change that adds
    such a call will fail this test loudly.
    """
    src = Path("src/fh6/application/services/shift/shift_event_evaluator.py").read_text()
    assert not re.search(r"\bupsert_bin\w*\(", src), (
        "FR-017 violation: shift event evaluator must not write to engine_curves"
    )


# ---------------------------------------------------------------------------
# FR-003: drift sessions never train
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_drift_session_never_trains_bins() -> None:
    repo = InMemoryShiftPredictorRepo()
    predictor = _make_predictor(repo)

    # Stable gear, full throttle, but the session is drift.
    for _ in range(20):
        await predictor.on_frame(
            _frame(),
            session_uptime_s=120.0,
            session_type="drift",
        )

    snap = predictor.get_snapshot(FP)
    assert snap.trained_sample_count == 0, (
        "FR-003 violation: drift session should not produce any training samples"
    )


# ---------------------------------------------------------------------------
# FR-020: displayActive false at low throttle even when learned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_display_active_false_at_low_throttle() -> None:
    repo = InMemoryShiftPredictorRepo()
    predictor = _make_predictor(repo)

    # Train with high throttle first
    for rpm in range(4000, 7800, 50):
        await predictor.on_frame(
            _frame(rpm=float(rpm)),
            session_uptime_s=120.0,
            session_type="race",
        )

    # Now serve a low-throttle frame — display must be off regardless of stage.
    deco = await predictor.on_frame(
        _frame(throttle=0.5),
        session_uptime_s=120.0,
        session_type="race",
    )
    assert deco.display_active is False, (
        "FR-020 violation: displayActive must be False below shift_display_throttle_min"
    )


# ---------------------------------------------------------------------------
# FR-023: reset clears bins, ratios, and shift events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_clears_everything() -> None:
    repo = InMemoryShiftPredictorRepo()
    predictor = _make_predictor(repo)

    # Seed the repo directly with one of each kind.
    now = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
    await repo.upsert_bin(
        BinRecord(
            fingerprint=FP,
            gear=4,
            rpm_bin=65,
            count=120,
            mean_torque_nm=410.0,
            m2_torque=200.0,
            q90_torque_nm=460.0,
            mean_boost_psi=0.0,
            last_updated=now,
        )
    )
    await repo.upsert_ratio(
        RatioRecord(
            fingerprint=FP,
            gear=4,
            ratio=160.0,
            variance=0.005,
            last_updated=now,
        )
    )
    await repo.record_shift_event(
        ShiftEventRow(
            id=None,
            session_id=SESSION_ID,
            fingerprint=FP,
            shift_at=now,
            gear_from=3,
            gear_to=4,
            actual_rpm=7100.0,
            recommended_rpm=7200.0,
            recommendation_conf=0.7,
            predicted_post_torque=400.0,
            measured_post_torque=380.0,
            est_cost_s=0.02,
        )
    )

    counts = await predictor.reset(FP)
    assert counts.engine_curves == 1
    assert counts.gear_ratios == 1
    assert counts.shift_events == 1

    assert await repo.read_bins(FP) == []
    assert await repo.read_ratios(FP) == []
    assert await repo.read_shift_events(SESSION_ID) == []


# ---------------------------------------------------------------------------
# Stage transitions: fallback → prior/learned as samples accumulate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stage_starts_at_fallback_when_cold() -> None:
    repo = InMemoryShiftPredictorRepo()
    predictor = _make_predictor(repo)
    snap = predictor.get_snapshot(FP)
    assert snap.stage == "fallback"


@pytest.mark.asyncio
async def test_stage_progresses_after_training() -> None:
    repo = InMemoryShiftPredictorRepo()
    predictor = _make_predictor(repo)

    # Drive a synthetic Gaussian-shaped torque curve across two adjacent
    # gears so the resolver can compute a crossover (and therefore
    # advance stage out of "fallback"). Each RPM bin needs at least
    # shift_bin_min_count (10) samples before the spline fit is used.
    for gear in (3, 4):
        # Stabilise the gear-stable filter for this gear
        for _ in range(20):
            await predictor.on_frame(
                _frame(gear=gear),
                session_uptime_s=120.0,
                session_type="race",
            )
        for _ in range(15):  # 15 passes × 76 bins ≈ 1140 samples / gear
            for rpm in range(4000, 7800, 50):
                torque = 400.0 * math.exp(-(((rpm - 6000.0) / 1500.0) ** 2))
                raw = _raw(gear=gear, rpm=float(rpm))
                raw.engine["torque"] = torque
                raw.engine["currentRpm"] = float(rpm)
                await predictor.on_frame(
                    DecodedFrame(
                        session_id=SESSION_ID,
                        car_id=CarId("c"),
                        received_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
                        raw=raw,
                    ),
                    session_uptime_s=120.0,
                    session_type="race",
                )
    snap = predictor.get_snapshot(FP)
    assert snap.stage in ("prior", "learned"), (
        f"after training, stage should advance from fallback; got {snap.stage}"
    )
    assert snap.trained_sample_count > 0


# ===========================================================================
# v2 safeguards (Task 18) — extend, don't replace
# ===========================================================================


# ---------------------------------------------------------------------------
# (a) FR-017 carry-over — confirm downshift code path doesn't upsert_bin.
# The v1 grep above already covers the whole file. This presence check
# guards against a future refactor silently deleting the downshift handler
# (which would cause the upshift handler to silently take downshift events).
# ---------------------------------------------------------------------------


def test_handle_downshift_method_exists() -> None:
    """FR-017 carry-over: the downshift branch must remain wired up.

    The v1 ``test_shift_event_evaluator_does_not_call_upsert_bin`` grep
    covers the whole evaluator file (including ``_handle_downshift``), so
    if ``_handle_downshift`` exists and there's no ``upsert_bin`` call,
    the FR-017 guarantee holds for downshifts too. This test pins the
    method's existence so the v1 grep keeps its coverage.
    """
    src = Path("src/fh6/application/services/shift/shift_event_evaluator.py").read_text()
    assert "_handle_downshift" in src, "downshift method missing — Task 15 incomplete"


# ---------------------------------------------------------------------------
# (b) FR-037 Signal A — slip-with-throttle rejects with "assist_intervention"
# ---------------------------------------------------------------------------


def _wot_frame_with_slip(slip: float) -> DecodedFrame:
    """A frame that passes every FR-003 driver/session clause except the
    slip-with-throttle check. Throttle is WOT (0.99) so the slip-threshold
    branch in ``training_filter`` is the only failure point.
    """
    raw = _raw(gear=4, rpm=6500.0, throttle=0.99)
    for corner in ("fl", "fr", "rl", "rr"):
        raw.wheels[corner]["combinedSlip"] = slip
    return DecodedFrame(
        session_id=SESSION_ID,
        car_id=CarId("car-001"),
        received_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        raw=raw,
    )


def _filter_inputs(cfg, *, recent_gears: list[int] | None = None) -> FilterInputs:
    return FilterInputs(
        config=cfg,
        is_drift_session=False,
        session_uptime_s=120.0,
        recent_gears=recent_gears if recent_gears is not None else [4, 4, 4, 4, 4, 4],
        recent_boost_psi=[],
        is_turbo=False,
    )


def test_fr_037_signal_a_rejects_high_slip_at_wot() -> None:
    """FR-037 Signal A: combinedSlip=0.6 at WOT rejects with reason
    'assist_intervention' (NOT 'slip') and intervention_suspected=True.

    The 0.50 default threshold is the unambiguous TCS-cut signature; the
    legacy 0.20 'slip' threshold from FR-003 already rejects these frames,
    but FR-037's whole point is that *which* reason fires matters for the
    intervention counter (FR-039).
    """
    cfg = _make_config()
    frame = _wot_frame_with_slip(0.6)
    fi = _filter_inputs(cfg)
    ai = AssistCheckInputs(
        class_prior_q90=None,
        tcs_slip_threshold=cfg.shift_tcs_slip_threshold,  # 0.50
        tcs_torque_floor_ratio=cfg.shift_tcs_torque_floor_ratio,
    )
    verdict = check_frame(frame, fi, ai)
    assert verdict.eligible is False
    assert verdict.reason == "assist_intervention", (
        f"FR-037 Signal A: expected 'assist_intervention', got {verdict.reason!r}"
    )
    assert verdict.intervention_suspected is True


# ---------------------------------------------------------------------------
# (c) FR-037 Signal B — torque deficit below class-prior ratio rejects
# ---------------------------------------------------------------------------


def test_fr_037_signal_b_rejects_torque_below_class_prior_ratio() -> None:
    """FR-037 Signal B: torque_nm < tcs_torque_floor_ratio * class_prior_q90
    at WOT rejects with reason 'assist_intervention'.

    Setup: class prior q90 = 500 Nm. Floor ratio default = 0.85, so the
    threshold is 425 Nm. Observed torque_nm = 300 Nm (well below 425).
    Frame is otherwise clean (low slip, WOT, etc.).
    """
    cfg = _make_config()
    raw = _raw(gear=4, rpm=6500.0, throttle=0.99)
    # Override torque: filter reads engine.get("torque_nm", 0.0)
    raw.engine["torque_nm"] = 300.0
    # Slip below the FR-037 Signal A threshold and below the legacy 'slip'
    # rejection threshold so Signal B is the only failure point.
    for corner in ("fl", "fr", "rl", "rr"):
        raw.wheels[corner]["combinedSlip"] = 0.05
    frame = DecodedFrame(
        session_id=SESSION_ID,
        car_id=CarId("car-001"),
        received_at=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        raw=raw,
    )
    fi = _filter_inputs(cfg)
    ai = AssistCheckInputs(
        class_prior_q90=500.0,
        tcs_slip_threshold=cfg.shift_tcs_slip_threshold,
        tcs_torque_floor_ratio=cfg.shift_tcs_torque_floor_ratio,  # 0.85
    )
    verdict = check_frame(frame, fi, ai)
    assert verdict.eligible is False
    assert verdict.reason == "assist_intervention", (
        f"FR-037 Signal B: expected 'assist_intervention', got {verdict.reason!r}"
    )
    assert verdict.intervention_suspected is True


# ---------------------------------------------------------------------------
# (d) FR-041 — TransmissionModeInferer excludes 1→2 samples
# ---------------------------------------------------------------------------


def test_fr_041_inferer_ignores_one_to_two_upshifts() -> None:
    """FR-041: the 1→2 launch-noise transition must not contribute to
    the dispersion classification.

    Drive a wildly-variable pre-shift RPM for 1→2 (5000, 6500, 7800, ...)
    alongside tight, consistent samples for 2→3 and 3→4. The inferer must
    classify 'auto' (low stdev) — proving the 1→2 samples were ignored.
    """
    cfg = _make_config()
    inferer = TransmissionModeInferer(config=cfg)

    # 1→2: wildly variable pre-shift RPMs (would push the median stdev
    # high if they were counted).
    one_to_two_rpms = [
        5000.0,
        6500.0,
        7800.0,
        4500.0,
        7200.0,
        5500.0,
        6000.0,
        7500.0,
        5800.0,
        7000.0,
        4800.0,
        6800.0,
    ]
    for rpm in one_to_two_rpms:
        inferer.observe_clean_upshift(FP, 1, 2, rpm)

    # 2→3 and 3→4: tight clusters around 7000 (stdev ≪ 50 → 'auto').
    tight_rpms = [
        6998.0,
        7001.0,
        7000.0,
        6999.0,
        7002.0,
        7000.0,
        6997.0,
        7003.0,
        6999.0,
        7001.0,
        7000.0,
        6998.0,
    ]
    for rpm in tight_rpms:
        inferer.observe_clean_upshift(FP, 2, 3, rpm)
    for rpm in tight_rpms:
        inferer.observe_clean_upshift(FP, 3, 4, rpm)

    result = inferer.infer(FP)
    assert result.mode == "auto", (
        f"FR-041 violation: 1→2 samples leaked into classification "
        f"(got mode={result.mode!r}). Tight 2→3 / 3→4 clusters should "
        f"yield 'auto'."
    )
    # The total sample count must NOT include 1→2 (the inferer's docstring
    # specifies sample_count counts non-1→2 samples only).
    assert result.sample_count == 2 * len(tight_rpms), (
        f"FR-041 violation: sample_count should exclude 1→2 transitions; "
        f"expected {2 * len(tight_rpms)}, got {result.sample_count}"
    )


# ---------------------------------------------------------------------------
# (e) FR-045 unviable downshift — solve_optimal(direction="down") returns None
# ---------------------------------------------------------------------------


def test_fr_045_unviable_downshift_returns_none() -> None:
    """FR-045: ``solve_optimal(direction='down')`` returns None when the
    post-shift gear's ratio is large enough that the entire pre-shift
    interval collapses below idle (every pre-shift RPM would over-rev
    the post-shift gear).

    With ratio_pre=100 and ratio_post=2500, the rpm_scale is 25 — meaning
    pre_rpm_max = max_rpm / 25 = 8000/25 = 320 RPM, which is below
    idle_rpm=900. Resolver returns None.
    """
    cfg = _make_config()
    resolver = ShiftCurveResolver(config=cfg)

    # Build a minimal CurveFit pair — any well-defined curves work; the
    # viability gate triggers before any of the math runs.
    bins = [
        BinRecord(
            fingerprint=FP,
            gear=3,
            rpm_bin=i,
            count=50,
            mean_torque_nm=350.0,
            m2_torque=100.0,
            q90_torque_nm=400.0,
            mean_boost_psi=0.0,
            last_updated=datetime(2026, 5, 23, 12, 0, tzinfo=UTC),
        )
        for i in range(20, 80)
    ]
    fit = resolver.fit_curve(bins, idle_rpm=900.0, max_rpm=8000.0)
    assert fit is not None, "test setup error: curve fit failed"

    result = resolver.solve_optimal(
        fit_pre=fit,
        fit_post=fit,
        ratio_pre=100.0,
        ratio_post=2500.0,
        direction="down",
        idle_rpm=900.0,
        max_rpm=8000.0,
    )
    assert result is None, (
        f"FR-045 violation: unviable downshift (ratio_post=2500, ratio_pre=100) "
        f"should return None; got {result}"
    )


# ---------------------------------------------------------------------------
# (f) FR-049 display gate — transmissionMode == "auto" forces displayActiveDown off
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fr_049_auto_transmission_suppresses_displayActiveDown() -> None:
    """FR-049: when ``transmissionMode.mode == 'auto'``, the downshift
    marker must be suppressed — even with an otherwise-viable downshift
    target, off-throttle/braking input, and learned stage.

    Approach: directly invoke ``_compute_display_active_down`` with all
    other clauses satisfied; flip only the transmission mode between
    'auto' and 'manual'. Auto must return False; manual True.
    """
    repo = InMemoryShiftPredictorRepo()
    predictor = _make_predictor(repo)

    # Otherwise-viable conditions: learned stage, throttle = 0 (off), brake = 0.4,
    # not drift, downshift target present (4800 RPM).
    common_kwargs = dict(
        stage="learned",
        throttle=0.0,
        brake=0.4,
        session_type="race",
        current_downshift_target=4800,
    )

    auto_block = TransmissionModeBlock(mode="auto", confidence=0.9)
    manual_block = TransmissionModeBlock(mode="manual", confidence=0.9)

    auto_gate = predictor._compute_display_active_down(
        transmission_mode=auto_block, **common_kwargs
    )
    manual_gate = predictor._compute_display_active_down(
        transmission_mode=manual_block, **common_kwargs
    )

    assert auto_gate is False, (
        "FR-049 violation: displayActiveDown must be False when "
        "transmissionMode.mode == 'auto', even with all other clauses satisfied"
    )
    assert manual_gate is True, (
        "FR-049 control: displayActiveDown must be True for manual transmission "
        "with all other clauses satisfied — guards against a too-strict gate"
    )


# ---------------------------------------------------------------------------
# (g) FR-044 reset extension — transmission_modes row is deleted and counted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fr_044_reset_deletes_transmission_modes_row() -> None:
    """FR-044 extends FR-023: reset must delete the matching
    transmission_modes row AND include the deleted count in the response
    (``ResetCounts.transmission_modes``).
    """
    repo = InMemoryShiftPredictorRepo()
    predictor = _make_predictor(repo)

    now = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
    # Seed the transmission_modes row directly (mimics a flush from a
    # previous session).
    await repo.upsert_transmission_mode(
        TransmissionModeRecord(
            fingerprint=FP,
            mode="auto",
            confidence=0.82,
            sample_count=24,
            last_updated=now,
        )
    )
    # Confirm it's there before the reset.
    assert await repo.read_transmission_mode(FP) is not None

    counts = await predictor.reset(FP)

    # Row is gone.
    assert await repo.read_transmission_mode(FP) is None, (
        "FR-044 violation: transmission_modes row should be deleted on reset"
    )
    # Count is reported in ResetCounts.
    assert counts.transmission_modes == 1, (
        f"FR-044 violation: expected transmission_modes=1 in ResetCounts, "
        f"got {counts.transmission_modes}"
    )
