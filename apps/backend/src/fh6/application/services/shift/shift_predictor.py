"""ShiftPredictor — top-level aggregate for shift recommendation (FR-008 to FR-022).

Orchestrates training (BinTrainer + RatioKalman), curve resolution, and
shift event detection. Returns a ShiftFrameDecoration for every live frame.

Collaborator protocols (CurveResolver, ClassPriorReader, ChangePointObserver,
ShiftEventListener) are defined here for Task 8; concrete implementations arrive
in Tasks 9-12. They are intentionally thin — method signatures are all that's
needed to allow injection and stubbing in tests.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from fh6.application.services.event_emitter import ShiftRecommendationProvider
from fh6.application.services.shift.bin_trainer import BinTrainer
from fh6.application.services.shift.ratio_kalman import RatioKalman
from fh6.application.services.shift.training_filter import (
    AssistCheckInputs,
    FilterInputs,
    check_frame,
)
from fh6.application.services.shift.transmission_mode import (
    TransmissionModeInferer,
    TransmissionModeResult,
)
from fh6.domain.entities.frame import DecodedFrame
from fh6.domain.ports.shift_predictor_repo import (
    ResetCounts,
    ShiftPredictorRepository,
    TransmissionModeRecord,
)
from fh6.domain.value_objects.engine_fingerprint import EngineClassKey, EngineFingerprint
from fh6.domain.value_objects.ids import SessionId
from fh6.infrastructure.config import AppConfig
from fh6.infrastructure.logging import get_logger

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Value object: ResolvedCurves
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResolvedCurves:
    """Output of CurveResolver.resolve() — per-gear-pair optimal RPMs + confidence.

    Includes both upshift (legacy v1) and downshift (FR-046) target maps.
    The downshift maps are keyed by *pre-shift* gear (the gear you're IN);
    a value of e.g. ``by_gear_downshift[3] == 4800`` means "the optimal
    pre-shift RPM for a 3->2 downshift is 4800". Keys are absent when the
    pair is unviable (FR-045) or when one of the two gears isn't fitted.
    """

    optimal_rpm_by_gear: dict[int, int]  # upshift target FROM this gear
    confidence_by_gear: dict[int, float]
    stage: str  # "learned" | "prior" | "fallback"
    samples_by_gear_pair: dict[tuple[int, int], int]  # for the training meter (upshift)
    # FR-046: downshift parallel maps. Default empty for backwards compat
    # with v1 callers (curve_resolver fills them when both gears are fitted).
    by_gear_downshift: dict[int, int] = field(default_factory=dict)
    confidence_by_gear_downshift: dict[int, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ShiftSnapshot:
    """Read-side projection used by /api/predict/shift (FR-021).

    Aggregates per-fingerprint training state into one immutable dict for
    the REST handler. `None` for `last_updated` means the predictor has
    seen no bins yet (cold start).
    """

    fingerprint: EngineFingerprint
    by_gear: dict[int, int]
    confidence_by_gear: dict[int, float]
    ratios: dict[int, float]
    ratio_confidence_by_gear: dict[int, float]
    stage: str
    trained_sample_count: int
    last_updated: datetime | None
    overall_confidence: float
    model_version: str = "shift-v1"


# ---------------------------------------------------------------------------
# Collaborator protocols
# ---------------------------------------------------------------------------


class CurveResolver(Protocol):
    """Computes per-gear-pair optimal RPMs + confidence from bins and ratios."""

    def resolve(
        self,
        bins: Any,
        ratios: Any,
        idle_rpm: float,
        max_rpm: float,
    ) -> ResolvedCurves: ...


class ClassPriorReader(Protocol):
    """Reads and rebuilds class-level prior bins (Task 10)."""

    async def read(self, key: Any) -> list[Any]: ...
    async def maybe_rebuild(
        self,
        key: Any,
        contributing_fp: Any,
        *,
        candidate_fingerprints: Sequence[Any] | None = None,
        excluded_paused: set[Any] | None = None,
        cooldown_s: int = 300,
        min_total_samples: int = 1_000,
    ) -> None:
        """Trigger a class-prior rebuild for `key`.

        Concrete implementations (``ClassPriorBuilder``) accept the v2
        kwargs ``candidate_fingerprints``, ``excluded_paused``,
        ``cooldown_s``, and ``min_total_samples`` (see FR-035). The
        Protocol keeps them as a passthrough ``**kwargs`` so v1-era fakes
        that only accept the positional args still satisfy the type.
        """
        ...


class ChangePointObserver(Protocol):
    """Observes per-bin change signals; can pause training on a fingerprint (Task 11)."""

    def observe(
        self,
        fp: EngineFingerprint,
        gear: int,
        rpm: float,
        torque_nm: float,
        at: datetime,
        stored_bin: Any,
    ) -> None: ...

    def reset(self, fp: EngineFingerprint) -> None: ...

    def is_paused(self, fp: EngineFingerprint) -> bool: ...


class ShiftEventListener(Protocol):
    """Notified when a shift event is detected by the predictor itself.

    The concrete implementation (``ShiftEventEvaluator``) needs more than
    the six basic args to evaluate cleanliness, fit predicted torque, and
    compute rev-match residuals. The Protocol mirrors the full 11-arg
    shape so static type-checkers and the predictor's call site agree.

    Snapshot types are ``Any`` because they're trainer-internal records
    (``BinRecord`` / ``RatioRecord`` keyed snapshots) not exported as part
    of the predictor's surface.
    """

    async def on_shift(
        self,
        session_id: Any,
        gear_from: int,
        gear_to: int,
        at: datetime,
        pre_window: Any,
        post_window: Any,
        *,
        fingerprint: EngineFingerprint,
        bins_snapshot: Any,
        ratios_snapshot: Any,
        recommended_rpm: float | None,
        recommendation_conf: float | None,
    ) -> None: ...


# ---------------------------------------------------------------------------
# Public value object: ShiftFrameDecoration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AssistInterventionBlock:
    """Per-frame assist-intervention metrics (FR-039).

    Reported in the shift decoration once a session has at least
    ``shift_assist_recent_window``-sized headroom — actually gated by the
    FR-040 floor of 100 eligible-or-intervened frames so the percentages
    have meaningful denominators.
    """

    recent_pct: float
    session_pct: float
    active: bool


@dataclass(frozen=True, slots=True)
class TransmissionModeBlock:
    """Per-frame transmission-mode classification (FR-042).

    Always present on the wire — including for ``mode="unknown"`` /
    ``confidence=0.0`` cold-start frames — so the frontend can render a
    consistent indicator from the very first frame.
    """

    mode: str  # "auto" | "manual" | "unknown"
    confidence: float  # 0.0 – 1.0


_UNKNOWN_TRANS_MODE_BLOCK = TransmissionModeBlock(mode="unknown", confidence=0.0)


@dataclass(frozen=True, slots=True)
class ShiftFrameDecoration:
    """Per-frame shift recommendation stamped onto modeled.shiftRecommendation."""

    by_gear: dict[int, int]  # upshift RPM target by gear (the gear you're IN)
    confidence_by_gear: dict[int, float]
    current_gear_target: int | None  # = by_gear[current_gear] OR None for top gear
    current_gear_confidence: float  # = confidence_by_gear[current_gear] OR 0
    display_active: bool  # FR-020
    stage: str  # "learned" | "prior" | "fallback"
    by_gear_samples: dict[int, int]  # samples accumulated per gear pair (current→next)
    fingerprint: dict[
        str, int | None
    ]  # {"carOrdinal": ..., "performanceIndex": ..., "numCylinders": ...}
    model_version: str = "shift-v1"
    # FR-039/FR-040: assist-intervention block. ``None`` until the per-session
    # eligible-or-intervened frame count crosses the FR-040 floor — when None,
    # the block is omitted from ``to_wire()`` so the frontend can hide the
    # indicator entirely.
    assist_intervention: AssistInterventionBlock | None = None
    # FR-042: transmission mode classification — always present (including
    # the "unknown" cold-start case). Defaults to the unknown block so
    # legacy call sites that don't yet propagate the inferer remain wire-compatible.
    transmission_mode: TransmissionModeBlock = _UNKNOWN_TRANS_MODE_BLOCK
    # FR-047: downshift parallel fields. Defaults keep v1 callers wire-compatible
    # (empty maps, no current-gear target). Keys in ``by_gear_downshift`` are
    # the *pre-shift* gear; gear 1 is never present (cannot downshift further);
    # any (g, g-1) pair whose post-shift RPM would over-rev has its key omitted
    # (FR-045 unviable case).
    by_gear_downshift: dict[int, int] = field(default_factory=dict)
    confidence_by_gear_downshift: dict[int, float] = field(default_factory=dict)
    current_gear_downshift_target: int | None = None
    current_gear_downshift_confidence: float = 0.0
    display_active_down: bool = False

    def to_wire(self) -> dict[str, Any]:
        """JSON-able dict matching FR-018 / FR-047 shape (camelCase keys).

        Returns the modeled.shiftRecommendation block.
        """
        out: dict[str, Any] = {
            "byGear": {str(k): v for k, v in self.by_gear.items()},
            "confidenceByGear": {str(k): v for k, v in self.confidence_by_gear.items()},
            "currentGearTarget": self.current_gear_target,
            "currentGearConfidence": self.current_gear_confidence,
            "displayActive": self.display_active,
            "stage": self.stage,
            "byGearSamples": {str(k): v for k, v in self.by_gear_samples.items()},
            "fingerprint": self.fingerprint,
            "modelVersion": self.model_version,
            "transmissionMode": {
                "mode": self.transmission_mode.mode,
                "confidence": self.transmission_mode.confidence,
            },
            # FR-047: downshift parallel fields. The maps are always present
            # (possibly empty); the current-gear scalars are None / 0.0 when
            # the active gear has no viable downshift pair.
            "byGearDownshift": {str(k): v for k, v in self.by_gear_downshift.items()},
            "confidenceByGearDownshift": {
                str(k): v for k, v in self.confidence_by_gear_downshift.items()
            },
            "currentGearDownshiftTarget": self.current_gear_downshift_target,
            "currentGearDownshiftConfidence": self.current_gear_downshift_confidence,
            "displayActiveDown": self.display_active_down,
        }
        if self.assist_intervention is not None:
            out["assistIntervention"] = {
                "recentPct": self.assist_intervention.recent_pct,
                "sessionPct": self.assist_intervention.session_pct,
                "active": self.assist_intervention.active,
            }
        return out


# ---------------------------------------------------------------------------
# Internal per-fingerprint mutable state
# ---------------------------------------------------------------------------

_RECENT_FRAMES_CAP = 10  # max frames kept in ring for pre-window extraction

# Default number of post-shift frames to accumulate before firing the listener.
# At 30 Hz, 20 frames ≈ 666 ms — covers FR-015's 300 ms NA / 500 ms turbo
# settling delay PLUS the 200 ms measurement window with a small margin.
_DEFAULT_POST_WINDOW_FRAMES = 20


@dataclass
class PendingShift:
    """A gear-change event awaiting enough post-shift frames to fire the listener.

    Enqueued at the moment a gear change is detected; each subsequent frame
    is appended to ``post_window`` until ``frames_needed`` is reached, at
    which point the ``ShiftEventListener`` is called with the fully-formed
    pre/post window pair.
    """

    session_id: SessionId | None
    at: datetime
    gear_from: int
    gear_to: int
    pre_window: list[DecodedFrame]  # snapshot taken at shift detection
    post_window: list[DecodedFrame] = field(default_factory=list)
    frames_needed: int = _DEFAULT_POST_WINDOW_FRAMES
    bins_snapshot: Any = None
    ratios_snapshot: Any = None
    recommended_rpm: float | None = None
    recommendation_conf: float | None = None
    fingerprint: EngineFingerprint | None = None


@dataclass
class _FingerprintState:
    """Mutable per-fingerprint training state tracked inside ShiftPredictor."""

    # Ring buffer of recent gear values for stability checks (length = gear_stable_frames+1)
    recent_gears: deque[int] = field(default_factory=deque)
    recent_gears_cap: int = 6

    # Ring buffer of recent boost PSI values for boost-settle checks (length = 5)
    recent_boost_psi: deque[float] = field(default_factory=lambda: deque(maxlen=5))

    # True once any boost > 1.0 psi observed in the session (sticky)
    is_turbo: bool = False

    # Accumulated sample count per gear (not gear-pair) for the training meter
    samples_by_gear: dict[int, int] = field(default_factory=dict)

    # Most recent resolved curves (None until first resolve call)
    cached_curves: ResolvedCurves | None = None

    # Count of new eligible samples since last curve resolve
    new_samples_since_resolve: int = 0

    # Previous frame's gear (to detect shift events)
    prev_gear: int | None = None

    # Recent frames ring for pre/post-window construction
    recent_frames: deque[DecodedFrame] = field(
        default_factory=lambda: deque(maxlen=_RECENT_FRAMES_CAP)
    )

    # Class-key of this fingerprint, captured on the first frame seen
    # (FR-036 — needed at flush time to trigger class-prior rebuilds).
    class_key: EngineClassKey | None = None

    # Pending shift events whose post_window is still accumulating.
    pending_shifts: list[PendingShift] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.recent_gears = deque(maxlen=self.recent_gears_cap)


# ---------------------------------------------------------------------------
# Session-scoped assist-intervention counters (FR-039, FR-040)
# ---------------------------------------------------------------------------

# Hardcoded cap for the recent ring buffer. The runtime-configurable value
# is ``cfg.shift_assist_recent_window``; we use it to size the deque on
# construction below.
_DEFAULT_ASSIST_RECENT_WINDOW = 900


@dataclass
class SessionAssistStats:
    """Per-session counters tracking assist-intervention frequency (FR-039).

    Only frames that pass FR-003 clauses 1-9 (race-on, not drift, warmup,
    throttle, brake, clutch, steer, gear, gear-stability) contribute. Among
    those, ``intervened_frames`` is the subset where the training filter
    raised an intervention-suspected verdict (slip exceeded
    ``tcs_slip_threshold``, or observed torque fell below
    ``tcs_torque_floor_ratio * class_prior_q90``).

    ``session_pct`` = intervened / eligible-or-intervened (lifetime, capped
    only by uint63 in practice).

    ``recent_pct`` = intervened / size of the recent ring (default 900
    frames ~= last 30 seconds at 30 Hz).
    """

    eligible_or_intervened_frames: int = 0
    intervened_frames: int = 0
    recent_window: deque[bool] = field(
        default_factory=lambda: deque(maxlen=_DEFAULT_ASSIST_RECENT_WINDOW)
    )

    def record(self, intervened: bool) -> None:
        self.eligible_or_intervened_frames += 1
        if intervened:
            self.intervened_frames += 1
        self.recent_window.append(intervened)

    def session_pct(self) -> float:
        return self.intervened_frames / max(1, self.eligible_or_intervened_frames)

    def recent_pct(self) -> float:
        if not self.recent_window:
            return 0.0
        return sum(self.recent_window) / len(self.recent_window)


# Reasons emitted by ``check_frame`` once the FR-003 driver/session checks
# (race-on..gear-stability) have passed. When the verdict carries one of
# these reasons, the frame is still "in a valid driving state" and should
# contribute to the assist-intervention counters. See plan Task 8 pseudocode.
_POST_DRIVER_REJECT_REASONS: frozenset[str] = frozenset(
    {"slip", "boost_unsettled", "assist_intervention"}
)


# ---------------------------------------------------------------------------
# ShiftPredictor
# ---------------------------------------------------------------------------


class ShiftPredictor:
    """Top-level aggregate: routes frames through training → curve resolution → decoration."""

    def __init__(
        self,
        *,
        config: AppConfig,
        repo: ShiftPredictorRepository,
        bin_trainer: BinTrainer,
        ratio_kalman: RatioKalman,
        curve_resolver: CurveResolver,
        class_prior: ClassPriorReader,
        change_point: ChangePointObserver,
        shift_listener: ShiftEventListener,
        transmission_mode_inferer: TransmissionModeInferer,
    ) -> None:
        self._cfg = config
        self._repo = repo
        self._bin_trainer = bin_trainer
        self._ratio_kalman = ratio_kalman
        self._curve_resolver = curve_resolver
        self._class_prior = (
            class_prior  # TODO: Task 10 will blend class priors into fallback curves
        )
        self._change_point = change_point
        self._shift_listener = shift_listener

        # FR-041/FR-042: transmission-mode inferer + persistence cache.
        # `_trans_mode_persisted` mirrors the latest persisted record so the
        # decoration can render from the start of the session; the
        # `_trans_mode_last_persisted_conf` map throttles ``upsert`` calls to
        # 0.1-confidence milestones.
        self._trans_mode = transmission_mode_inferer
        self._trans_mode_persisted: dict[EngineFingerprint, TransmissionModeResult] = {}
        self._trans_mode_last_persisted_conf: dict[EngineFingerprint, float] = {}
        # Fingerprints that have received at least one ``observe_clean_upshift``
        # since the last flush. Flush will unconditionally persist their current
        # in-memory state (FR-043).
        self._trans_mode_touched: set[EngineFingerprint] = set()

        # Per-fingerprint mutable state
        self._states: dict[EngineFingerprint, _FingerprintState] = {}

        # FR-039/FR-040: per-session assist-intervention counters. Keyed by
        # SessionId. A predictor instance is process-scoped, so this dict
        # accumulates across the lifetime of the process; sessions clean up
        # via ``session_started`` (currently a no-op hook called by the
        # session_manager — Task 14 binds it).
        self._assist_stats: dict[SessionId, SessionAssistStats] = {}

        # Strong references to in-flight class-prior rebuild tasks (FR-036).
        # Without this set the tasks would be eligible for GC before completion
        # because asyncio.create_task only keeps a weak reference internally.
        self._pending_class_prior_rebuilds: set[asyncio.Task[None]] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def on_frame(
        self,
        frame: DecodedFrame,
        *,
        session_uptime_s: float,
        session_type: str,
    ) -> ShiftFrameDecoration:
        """Process one live frame and return a ShiftFrameDecoration.

        Returns a decoration even for ineligible frames (echoes last known
        recommendation; flips display_active off as appropriate).
        """
        raw = frame.raw

        # --- Step 1: Extract fingerprint ---
        fp = EngineFingerprint.from_frame_raw(raw)
        max_rpm: float = float(raw.engine.get("maxRpm", 8000.0))
        idle_rpm: float = float(raw.engine.get("idleRpm", 900.0))

        if not fp.is_complete():
            return self._fallback_decoration(fp, max_rpm)

        # --- Step 2: Get/create per-fingerprint state ---
        state = self._get_or_create_state(fp)

        # Record the class-key of this fingerprint on first sighting so
        # flush() can trigger per-class-key prior rebuilds (FR-036).
        if state.class_key is None:
            state.class_key = EngineClassKey.from_frame_raw(raw)

        current_gear: int = int(raw.drivetrain.get("gear", 0))
        rpm: float = float(raw.engine.get("rpm", raw.engine.get("currentRpm", 0.0)))
        # Canonical decoder keys are ``torque_nm`` and ``boost_psi``
        # (``fh6_decoder.FrameRaw.engine``). Fall back to the legacy ``torque``
        # / ``boost`` keys for hand-built test frames that haven't migrated.
        torque_nm: float = float(raw.engine.get("torque_nm", raw.engine.get("torque", 0.0)))
        boost_psi: float = float(raw.engine.get("boost_psi", raw.engine.get("boost", 0.0)))
        throttle: float = float(raw.inputs.get("throttle", 0.0))
        brake: float = float(raw.inputs.get("brake", 0.0))
        speed_mps: float = float(raw.motion.get("speed", 0.0))
        at: datetime = frame.received_at or datetime.now(tz=UTC)

        # Sticky turbo detection
        if boost_psi > 1.0:
            state.is_turbo = True

        # --- Step 3a: Drain any pending shifts with this incoming frame ---
        # Each pending shift accumulates post-shift frames until ``frames_needed``
        # is reached; we fire the listener then drop the pending. This must run
        # BEFORE the gear-change detection below so the post_window of the
        # *previous* shift sees today's pre-detection frame, and so a brand-new
        # shift enqueued below doesn't immediately get this frame appended.
        if state.pending_shifts:
            await self._drain_pending_shifts(state, frame)

        # --- Step 3b: Detect shift event ---
        # On gear change, enqueue a PendingShift snapshot. The listener fires
        # later once enough post-shift frames have accumulated (FR-015 settling
        # delay + 200 ms measurement window).
        prev_gear = state.prev_gear
        if (
            prev_gear is not None
            and current_gear != prev_gear
            and current_gear > 0
            and prev_gear > 0
        ):
            pre_window = list(state.recent_frames)
            # Direction-aware recommendation lookup from the cached curves.
            # Upshift (gear_to > prev_gear): use the upshift target FROM prev_gear.
            # Downshift (gear_to < prev_gear): use the downshift target FROM prev_gear.
            # ``.get()`` returns None for cold-start / unviable cases.
            recommended_rpm_at_shift: float | None = None
            recommendation_conf_at_shift: float | None = None
            if state.cached_curves is not None:
                if current_gear > prev_gear:
                    target = state.cached_curves.optimal_rpm_by_gear.get(prev_gear)
                    conf = state.cached_curves.confidence_by_gear.get(prev_gear)
                else:
                    target = state.cached_curves.by_gear_downshift.get(prev_gear)
                    conf = state.cached_curves.confidence_by_gear_downshift.get(prev_gear)
                recommended_rpm_at_shift = float(target) if target is not None else None
                recommendation_conf_at_shift = float(conf) if conf is not None else None
            state.pending_shifts.append(
                PendingShift(
                    session_id=frame.session_id,
                    at=at,
                    gear_from=prev_gear,
                    gear_to=current_gear,
                    pre_window=pre_window,
                    post_window=[],
                    fingerprint=fp,
                    bins_snapshot=self._bin_trainer.snapshot(fp),
                    ratios_snapshot=self._ratio_kalman.snapshot(fp),
                    recommended_rpm=recommended_rpm_at_shift,
                    recommendation_conf=recommendation_conf_at_shift,
                )
            )
            # FR-042: also feed the transmission-mode inferer (Task 11 wiring).
            # The pre-shift RPM is the last frame in recent_frames (the most
            # recent frame BEFORE this gear-change frame is appended below).
            # is_clean_upshift uses direction-only cleanliness: the inferer's
            # own guards drop 1→2 transitions and non-adjacent jumps, and the
            # transmission-mode classifier is robust to occasional noise via
            # its median-of-stdevs aggregation.
            if pre_window:
                pre_shift_rpm = float(
                    pre_window[-1].raw.engine.get(
                        "rpm", pre_window[-1].raw.engine.get("currentRpm", 0.0)
                    )
                )
                is_clean_upshift = current_gear == prev_gear + 1 and prev_gear > 0
                await self.on_shift_event(
                    fp=fp,
                    gear_from=prev_gear,
                    gear_to=current_gear,
                    pre_shift_rpm=pre_shift_rpm,
                    is_clean_upshift=is_clean_upshift,
                )

        # Update prev_gear and recent_frames ring
        state.prev_gear = current_gear
        state.recent_frames.append(frame)

        # --- Step 4: Run training filter ---
        fi = FilterInputs(
            config=self._cfg,
            is_drift_session=(session_type == "drift"),
            session_uptime_s=session_uptime_s,
            recent_gears=list(state.recent_gears),
            recent_boost_psi=list(state.recent_boost_psi),
            is_turbo=state.is_turbo,
        )
        # FR-037/FR-038: assist-intervention inputs. The class-prior q90
        # lookup is keyed by the active fingerprint's class-key + (gear,
        # rpm_bin); returns None for cold starts / unbinned cells, in which
        # case Signal B is skipped (Signal A — slip-band — still runs).
        rpm_bin = int(rpm / 100.0)
        class_prior_q90 = await self._lookup_prior_q90(state.class_key, current_gear, rpm_bin)
        ai = AssistCheckInputs(
            class_prior_q90=class_prior_q90,
            tcs_slip_threshold=self._cfg.shift_tcs_slip_threshold,
            tcs_torque_floor_ratio=self._cfg.shift_tcs_torque_floor_ratio,
        )
        verdict = check_frame(frame, fi, ai)

        # Always update ring buffers (so future eligibility checks reflect new gear/boost)
        state.recent_gears.append(current_gear)
        if boost_psi > 0.0 or state.is_turbo:
            state.recent_boost_psi.append(boost_psi)

        # FR-039: record assist-intervention counters. Only frames that
        # passed the FR-003 driver/session preconditions contribute — those
        # are the verdict-eligible frames plus the few reject reasons that
        # come from clauses 10+ (slip-band, boost-unsettled, assist).
        session_id = frame.session_id
        if session_id is not None and (
            verdict.eligible or verdict.reason in _POST_DRIVER_REJECT_REASONS
        ):
            assist_stats = self._assist_stats.setdefault(session_id, self._make_assist_stats())
            assist_stats.record(verdict.intervention_suspected)

        if not verdict.eligible:
            # Echo last curves; force display_active off per FR-020.
            # ``brake`` is still propagated so the downshift display gate
            # (FR-049) can flip on during corner approaches where the frame
            # is ineligible for training (brake > shift_brake_max) but the
            # downshift marker should be visible.
            return self._decoration_from_cache(
                fp=fp,
                state=state,
                current_gear=current_gear,
                throttle=throttle,
                session_type=session_type,
                session_id=session_id,
                brake=brake,
            )

        # --- Step 5: Eligible path ---
        training_paused = self._change_point.is_paused(fp)

        if not training_paused:
            # Update bin statistics
            self._bin_trainer.update(fp, current_gear, rpm, torque_nm, boost_psi, at)

            # Update gear ratio Kalman filter (skip if speed too low)
            if speed_mps >= 1.0 and rpm > 0.0:
                ratio_measurement = rpm / speed_mps
                self._ratio_kalman.update(fp, current_gear, ratio_measurement)

            # Notify change-point observer with the post-update stored bin
            stored_bins = self._bin_trainer.snapshot(fp)
            stored_bin = stored_bins.get((current_gear, int(rpm / 100.0)))
            self._change_point.observe(fp, current_gear, rpm, torque_nm, at, stored_bin)

            # Update sample counter
            state.new_samples_since_resolve += 1
            state.samples_by_gear[current_gear] = state.samples_by_gear.get(current_gear, 0) + 1
        # NOTE: When training is paused (Task 11 change-point), we skip bin/Kalman
        # updates but still run curve resolution from the cached bins so decorations
        # keep emitting. The _paused flag is observable via change_point.is_paused(fp).

        # --- Resolve curves if needed ---
        if (
            state.cached_curves is None
            or state.new_samples_since_resolve >= self._cfg.shift_recompute_every_n
        ):
            bins = self._bin_trainer.snapshot(fp)
            ratios = self._ratio_kalman.snapshot(fp)
            curves = self._curve_resolver.resolve(bins, ratios, idle_rpm, max_rpm)
            state.cached_curves = curves
            state.new_samples_since_resolve = 0

        # --- Build decoration ---
        return self._decoration_from_cache(
            fp=fp,
            state=state,
            current_gear=current_gear,
            throttle=throttle,
            session_type=session_type,
            session_id=session_id,
            brake=brake,
        )

    async def hydrate_for_session(
        self, session_id: SessionId, fingerprint: EngineFingerprint
    ) -> None:
        """Load bins + ratios from the repo for this fingerprint.

        No-op if the fingerprint is incomplete.
        """
        if not fingerprint.is_complete():
            return

        bins = await self._repo.read_bins(fingerprint)
        ratios = await self._repo.read_ratios(fingerprint)

        self._bin_trainer.hydrate(fingerprint, bins)
        self._ratio_kalman.hydrate(fingerprint, ratios)

        # FR-042: hydrate the persisted transmission-mode cache so the wire
        # decoration reports the persisted classification from the very first
        # frame, before the in-memory inferer has accumulated fresh samples.
        persisted = await self._repo.read_transmission_mode(fingerprint)
        if persisted is not None:
            self._trans_mode_persisted[fingerprint] = TransmissionModeResult(
                mode=persisted.mode,
                confidence=persisted.confidence,
                sample_count=persisted.sample_count,
            )
            self._trans_mode_last_persisted_conf[fingerprint] = persisted.confidence

    async def flush(self) -> None:
        """Persist all in-memory state for currently-tracked fingerprints.

        After persisting bins and ratios, schedules a class-prior rebuild
        (FR-036) for each class-key whose touched fingerprints have at
        least ``shift_prior_min_fp_samples`` total bin samples. Rebuilds
        run as background tasks so they never block the flush call.

        In-flight rebuild tasks are kept alive via
        ``_pending_class_prior_rebuilds`` (strong references). Production
        callers can fire-and-forget; tests can inspect via
        ``pending_class_prior_rebuilds()``.
        """
        # Fire any pending shifts before persisting anything else: each
        # pending event represents a real gear change the listener hasn't
        # heard about yet. We'd rather emit with a short post_window
        # (cleanliness checks downstream may then reject it) than lose the
        # event entirely when the session ends.
        for state in self._states.values():
            if not state.pending_shifts:
                continue
            pendings = state.pending_shifts
            state.pending_shifts = []
            for pending in pendings:
                await self._fire_pending_shift(pending)

        await self._bin_trainer.flush(self._repo)
        await self._ratio_kalman.flush(self._repo)

        # FR-043: unconditionally persist current in-memory transmission-mode
        # state for each fingerprint touched since the last flush. Skips
        # fingerprints whose inferer hasn't produced a real classification yet.
        for fp in list(self._trans_mode_touched):
            result = self._trans_mode.infer(fp)
            if result.mode == "unknown":
                continue
            await self._repo.upsert_transmission_mode(
                TransmissionModeRecord(
                    fingerprint=fp,
                    mode=result.mode,
                    confidence=result.confidence,
                    sample_count=result.sample_count,
                    last_updated=datetime.now(tz=UTC),
                )
            )
            self._trans_mode_persisted[fp] = result
            self._trans_mode_last_persisted_conf[fp] = result.confidence
        self._trans_mode_touched.clear()

        # FR-036: trigger class-prior rebuild for each class-key whose
        # touched fingerprints have enough samples to contribute.
        paused: set[EngineFingerprint] = {
            fp for fp in self._states if self._change_point.is_paused(fp)
        }

        # Group qualifying fingerprints by class_key. A fingerprint
        # qualifies if its persisted bin-count total meets the threshold.
        by_class: dict[EngineClassKey, list[EngineFingerprint]] = {}
        for fp, st in self._states.items():
            if st.class_key is None:
                continue
            total = sum(b.count for b in (await self._repo.read_bins(fp)))
            if total >= self._cfg.shift_prior_min_fp_samples:
                by_class.setdefault(st.class_key, []).append(fp)

        for class_key, fps in by_class.items():
            contributing = fps[0]  # any qualifying fingerprint serves as the trigger source
            candidates = [fp for fp, st in self._states.items() if st.class_key == class_key]
            task = asyncio.create_task(
                self._safely_rebuild_class_prior(
                    class_key,
                    contributing,
                    candidates,
                    paused,
                )
            )
            self._pending_class_prior_rebuilds.add(task)
            task.add_done_callback(self._pending_class_prior_rebuilds.discard)

    def pending_class_prior_rebuilds(self) -> frozenset[asyncio.Task[None]]:
        """Return the set of currently-pending class-prior rebuild tasks.

        Exposed for tests; production callers do not need to await these.
        """
        return frozenset(self._pending_class_prior_rebuilds)

    def on_session_started(self, session_id: SessionId) -> None:
        """Hook called by SessionManager when a new session begins.

        Resets per-session state: assist counters. Curve / ratio / change-point
        state is keyed by fingerprint and persists across sessions.
        """
        self._assist_stats.pop(session_id, None)

    def get_session_assist_pct(self, session_id: SessionId) -> float:
        """Return the lifetime session-level assist-intervention percentage (FR-051).

        Returns ``_assist_stats[session_id].session_pct()`` when the session has
        at least one recorded frame; 0.0 otherwise (cold-start / session not seen).

        NOTE: This counter is in-memory only and is **not** persisted by the
        current plan.  Historical sessions (i.e., any session that is not the
        currently-active in-flight session) will therefore report 0.0 once the
        process restarts.  The /report endpoint calls this out in its docstring.
        """
        stats = self._assist_stats.get(session_id)
        if stats is None:
            return 0.0
        return stats.session_pct()

    async def on_shift_event(
        self,
        *,
        fp: EngineFingerprint,
        gear_from: int,
        gear_to: int,
        pre_shift_rpm: float,
        is_clean_upshift: bool,
    ) -> None:
        """Hook invoked once per detected shift event (FR-042).

        Task 11 will subscribe this method to the ``EventEmitter`` shift-listener
        hook so production traffic flows through here. For Task 10, callers
        invoke it directly.

        Only clean upshifts to the immediately-next gear feed the inferer; the
        inferer itself further filters 1→2 transitions (launch noise — FR-041).
        """
        if not is_clean_upshift:
            return
        if gear_to != gear_from + 1:
            return
        self._trans_mode.observe_clean_upshift(fp, gear_from, gear_to, pre_shift_rpm)
        self._trans_mode_touched.add(fp)
        await self._maybe_persist_trans_mode(fp)

    async def _maybe_persist_trans_mode(self, fp: EngineFingerprint) -> None:
        """Persist the current in-memory transmission-mode result for *fp* if
        the classification has changed or confidence has stepped by ≥ 0.1
        since the last persist (FR-042).
        """
        result = self._trans_mode.infer(fp)
        if result.mode == "unknown":
            return
        last_conf = self._trans_mode_last_persisted_conf.get(fp, -1.0)
        persisted = self._trans_mode_persisted.get(fp)
        mode_changed = persisted is None or persisted.mode != result.mode
        conf_jumped = (result.confidence - last_conf) >= 0.1
        if not (mode_changed or conf_jumped):
            return
        await self._repo.upsert_transmission_mode(
            TransmissionModeRecord(
                fingerprint=fp,
                mode=result.mode,
                confidence=result.confidence,
                sample_count=result.sample_count,
                last_updated=datetime.now(tz=UTC),
            )
        )
        self._trans_mode_persisted[fp] = result
        self._trans_mode_last_persisted_conf[fp] = result.confidence

    async def _safely_rebuild_class_prior(
        self,
        class_key: EngineClassKey,
        contributing_fp: EngineFingerprint,
        candidates: Sequence[EngineFingerprint],
        paused: set[EngineFingerprint],
    ) -> None:
        """Invoke ``class_prior.maybe_rebuild`` with v2 kwargs, swallowing errors.

        Errors are logged but never propagated — flush must remain
        side-effect-only from the caller's perspective (FR-036).
        """
        try:
            await self._class_prior.maybe_rebuild(
                class_key,
                contributing_fp,
                candidate_fingerprints=candidates,
                excluded_paused=paused,
                cooldown_s=self._cfg.shift_prior_rebuild_cooldown_s,
                min_total_samples=self._cfg.shift_prior_min_fp_samples,
            )
        except Exception:
            _log.exception(
                "class_prior_rebuild_failed class_key=%s fp=%s",
                class_key,
                contributing_fp,
            )

    async def reset(self, fp: EngineFingerprint) -> ResetCounts:
        """Clear in-memory + on-disk state for fp; return ResetCounts."""
        # Clear in-memory state
        self._states.pop(fp, None)

        # Clear bin trainer and ratio kalman state for this fp
        # (hydrate with empty list effectively clears the fp)
        self._bin_trainer.hydrate(fp, [])
        self._ratio_kalman.hydrate(fp, [])

        # Reset change-point window for this fp
        with contextlib.suppress(AttributeError):
            self._change_point.reset(fp)

        # FR-042: drop the inferer's in-memory ring + the persisted cache so
        # downstream decorations don't echo stale classifications.
        self._trans_mode.drop_fingerprint(fp)
        self._trans_mode_persisted.pop(fp, None)
        self._trans_mode_last_persisted_conf.pop(fp, None)
        self._trans_mode_touched.discard(fp)

        # Delegate to repo for on-disk clearing
        counts = await self._repo.reset_fingerprint(fp)
        # FR-044: also delete the transmission_modes DB row and include the
        # deleted count in the returned ResetCounts value object.
        transmission_deleted = await self._repo.delete_transmission_mode(fp)
        return ResetCounts(
            engine_curves=counts.engine_curves,
            gear_ratios=counts.gear_ratios,
            shift_events=counts.shift_events,
            transmission_modes=transmission_deleted,
        )

    def get_snapshot(self, fp: EngineFingerprint) -> ShiftSnapshot:
        """Build a ShiftSnapshot for REST consumption (FR-021).

        Reads from cached curves (if resolved) + Kalman ratios + bin counts.
        Falls back to an empty snapshot with stage="fallback" when the
        predictor has never seen this fingerprint.
        """
        state = self._states.get(fp)
        ratios_snap = self._ratio_kalman.snapshot(fp)
        ratios: dict[int, float] = {g: r.ratio for g, r in ratios_snap.items()}
        ratio_conf: dict[int, float] = {
            g: max(0.0, min(1.0, 1.0 / (1.0 + r.variance))) for g, r in ratios_snap.items()
        }

        # Sum sample counts and find last update across bins
        bins_snap = self._bin_trainer.snapshot(fp)
        trained_count = sum(int(rec.count) for rec in bins_snap.values())
        last_updated: datetime | None = None
        for rec in bins_snap.values():
            if last_updated is None or rec.last_updated > last_updated:
                last_updated = rec.last_updated

        if state is None or state.cached_curves is None:
            return ShiftSnapshot(
                fingerprint=fp,
                by_gear={},
                confidence_by_gear={},
                ratios=ratios,
                ratio_confidence_by_gear=ratio_conf,
                stage="fallback",
                trained_sample_count=trained_count,
                last_updated=last_updated,
                overall_confidence=0.0,
            )

        curves = state.cached_curves
        by_gear = dict(curves.optimal_rpm_by_gear)
        conf_by_gear = dict(curves.confidence_by_gear)

        # Overall confidence: weighted mean over gears with locked ratios.
        locked_gears = [g for g, r in ratios_snap.items() if r.variance < 1.0]
        if locked_gears:
            relevant = [conf_by_gear.get(g, 0.0) for g in locked_gears if g in conf_by_gear]
            overall = sum(relevant) / len(relevant) if relevant else 0.0
        elif conf_by_gear:
            overall = sum(conf_by_gear.values()) / len(conf_by_gear)
        else:
            overall = 0.0

        return ShiftSnapshot(
            fingerprint=fp,
            by_gear=by_gear,
            confidence_by_gear=conf_by_gear,
            ratios=ratios,
            ratio_confidence_by_gear=ratio_conf,
            stage=curves.stage,
            trained_sample_count=trained_count,
            last_updated=last_updated,
            overall_confidence=overall,
        )

    def recommendation_provider(self) -> ShiftRecommendationProvider:
        """Return an object satisfying ShiftRecommendationProvider for the EventEmitter.

        The returned helper reads from the predictor's in-memory state at
        shift-emission time and returns the current-gear recommendation +
        confidence (or None when no recommendation is available).
        """
        predictor = self

        class _Provider:
            def get_recommendation(self, frame: DecodedFrame) -> tuple[float, float] | None:
                fp = EngineFingerprint.from_frame_raw(frame.raw)
                if not fp.is_complete():
                    return None
                state = predictor._states.get(fp)
                if state is None or state.cached_curves is None:
                    return None
                current_gear = int(frame.raw.drivetrain.get("gear", 0))
                target = state.cached_curves.optimal_rpm_by_gear.get(current_gear)
                if target is None:
                    return None
                conf = state.cached_curves.confidence_by_gear.get(current_gear, 0.0)
                return (float(target), float(conf))

        return _Provider()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _drain_pending_shifts(self, state: _FingerprintState, frame: DecodedFrame) -> None:
        """Append ``frame`` to each pending shift's post_window and fire any
        that have reached ``frames_needed`` frames.

        Multiple pendings can coexist (a new gear change before the previous
        one has filled its post window); each carries its own pre_window
        snapshot and progresses independently.
        """
        ready: list[PendingShift] = []
        for pending in state.pending_shifts:
            pending.post_window.append(frame)
            if len(pending.post_window) >= pending.frames_needed:
                ready.append(pending)
        for pending in ready:
            state.pending_shifts.remove(pending)
            await self._fire_pending_shift(pending)

    async def _fire_pending_shift(self, pending: PendingShift) -> None:
        """Invoke the ShiftEventListener with the full pending payload."""
        assert pending.fingerprint is not None  # set on enqueue
        await self._shift_listener.on_shift(
            pending.session_id,
            pending.gear_from,
            pending.gear_to,
            pending.at,
            pending.pre_window,
            pending.post_window,
            fingerprint=pending.fingerprint,
            bins_snapshot=pending.bins_snapshot,
            ratios_snapshot=pending.ratios_snapshot,
            recommended_rpm=pending.recommended_rpm,
            recommendation_conf=pending.recommendation_conf,
        )

    def _get_or_create_state(self, fp: EngineFingerprint) -> _FingerprintState:
        state = self._states.get(fp)
        if state is None:
            cap = self._cfg.shift_gear_stable_frames + 1
            state = _FingerprintState(recent_gears_cap=cap)
            self._states[fp] = state
        return state

    def _fallback_decoration(self, fp: EngineFingerprint, max_rpm: float) -> ShiftFrameDecoration:
        """Return a fallback decoration for an incomplete fingerprint."""
        fallback_target = round(0.875 * max_rpm / 100) * 100
        return ShiftFrameDecoration(
            by_gear={},
            confidence_by_gear={},
            current_gear_target=fallback_target,
            current_gear_confidence=0.0,
            display_active=False,
            stage="fallback",
            by_gear_samples={},
            fingerprint={
                "carOrdinal": fp.car_ordinal,
                "performanceIndex": fp.performance_index,
                "numCylinders": fp.num_cylinders,
            },
            transmission_mode=self._resolve_trans_mode_for_frame(fp),
        )

    def _decoration_from_cache(
        self,
        *,
        fp: EngineFingerprint,
        state: _FingerprintState,
        current_gear: int,
        throttle: float,
        session_type: str,
        session_id: SessionId | None = None,
        brake: float = 0.0,
    ) -> ShiftFrameDecoration:
        """Build a decoration from cached curves (or fallback if no cache yet)."""
        ai_block = self._build_assist_block(session_id)
        trans_mode_block = self._resolve_trans_mode_for_frame(fp)

        if state.cached_curves is None:
            # No curves resolved yet — return a simple fallback
            return ShiftFrameDecoration(
                by_gear={},
                confidence_by_gear={},
                current_gear_target=None,
                current_gear_confidence=0.0,
                display_active=False,
                stage="fallback",
                by_gear_samples=dict(state.samples_by_gear),
                fingerprint={
                    "carOrdinal": fp.car_ordinal,
                    "performanceIndex": fp.performance_index,
                    "numCylinders": fp.num_cylinders,
                },
                assist_intervention=ai_block,
                transmission_mode=trans_mode_block,
            )

        curves = state.cached_curves
        by_gear = curves.optimal_rpm_by_gear
        # FR-011 / FR-013: drift_penalty is applied post-hoc at decoration
        # time so the cached ResolvedCurves.confidence_by_gear stays
        # drift-agnostic across change-point transitions. When training is
        # paused on this fingerprint, every per-gear confidence is multiplied
        # by (1 - 0.5) = 0.5.
        drift_penalty = 0.5 if self._change_point.is_paused(fp) else 0.0
        drift_factor = 1.0 - drift_penalty
        confidence_by_gear = {g: c * drift_factor for g, c in curves.confidence_by_gear.items()}

        # current_gear_target: None if current gear is the top gear (no higher gear)
        current_gear_target = by_gear.get(current_gear)
        current_gear_confidence = confidence_by_gear.get(current_gear, 0.0)

        # Compute by_gear_samples from samples_by_gear_pair
        # Map gear -> sample count of the (gear, gear+1) pair
        by_gear_samples: dict[int, int] = {}
        for (g_from, _g_to), count in curves.samples_by_gear_pair.items():
            by_gear_samples[g_from] = count

        # FR-020 display gate
        display_active = self._compute_display_active(
            stage=curves.stage,
            throttle=throttle,
            session_type=session_type,
        )

        # FR-047: downshift parallel fields. ``by_gear_downshift`` is keyed by
        # the pre-shift gear; the current-gear scalar tracks that map. The
        # downshift confidence map is also drift-penalty-adjusted.
        by_gear_downshift = curves.by_gear_downshift
        conf_by_gear_downshift = {
            g: c * drift_factor for g, c in curves.confidence_by_gear_downshift.items()
        }
        current_gear_downshift_target = (
            by_gear_downshift.get(current_gear) if current_gear >= 2 else None
        )
        current_gear_downshift_confidence = (
            conf_by_gear_downshift.get(current_gear, 0.0) if current_gear >= 2 else 0.0
        )

        # FR-049 display gate for the downshift marker. Independent of FR-020
        # (the upshift gate) — both markers can be off, both on, or either.
        display_active_down = self._compute_display_active_down(
            stage=curves.stage,
            throttle=throttle,
            brake=brake,
            session_type=session_type,
            transmission_mode=trans_mode_block,
            current_downshift_target=current_gear_downshift_target,
        )

        return ShiftFrameDecoration(
            by_gear=dict(by_gear),
            confidence_by_gear=dict(confidence_by_gear),
            current_gear_target=current_gear_target,
            current_gear_confidence=current_gear_confidence,
            display_active=display_active,
            stage=curves.stage,
            by_gear_samples=by_gear_samples,
            fingerprint={
                "carOrdinal": fp.car_ordinal,
                "performanceIndex": fp.performance_index,
                "numCylinders": fp.num_cylinders,
            },
            assist_intervention=ai_block,
            transmission_mode=trans_mode_block,
            by_gear_downshift=dict(by_gear_downshift),
            confidence_by_gear_downshift=dict(conf_by_gear_downshift),
            current_gear_downshift_target=current_gear_downshift_target,
            current_gear_downshift_confidence=current_gear_downshift_confidence,
            display_active_down=display_active_down,
        )

    def _resolve_trans_mode_for_frame(self, fp: EngineFingerprint) -> TransmissionModeBlock:
        """Pick the best transmission-mode block for the current frame.

        Prefers the inferer's live result when its sample count exceeds the
        persisted snapshot's — that way fresh in-session learning shines
        through even between persistence milestones. Falls back to the
        persisted snapshot when no fresh samples have arrived yet.
        """
        live = self._trans_mode.infer(fp)
        persisted = self._trans_mode_persisted.get(fp)
        if persisted is None:
            return TransmissionModeBlock(mode=live.mode, confidence=live.confidence)
        if live.sample_count > persisted.sample_count:
            return TransmissionModeBlock(mode=live.mode, confidence=live.confidence)
        return TransmissionModeBlock(mode=persisted.mode, confidence=persisted.confidence)

    def _build_assist_block(self, session_id: SessionId | None) -> AssistInterventionBlock | None:
        """Return the assist-intervention block for ``session_id`` or None.

        FR-040 floor: the block is None until the session has accumulated
        at least 100 eligible-or-intervened frames. Below the floor the
        denominators are too noisy to be informative and the wire field
        is omitted entirely so the frontend can hide the indicator.
        """
        if session_id is None:
            return None
        stats = self._assist_stats.get(session_id)
        if stats is None or stats.eligible_or_intervened_frames < 100:
            return None
        recent = stats.recent_pct()
        return AssistInterventionBlock(
            recent_pct=recent,
            session_pct=stats.session_pct(),
            active=(recent >= self._cfg.shift_assist_alert_pct),
        )

    def _make_assist_stats(self) -> SessionAssistStats:
        """Construct a SessionAssistStats with the config-sized recent ring."""
        return SessionAssistStats(
            recent_window=deque(maxlen=self._cfg.shift_assist_recent_window),
        )

    async def _lookup_prior_q90(
        self,
        class_key: EngineClassKey | None,
        gear: int,
        rpm_bin: int,
    ) -> float | None:
        """Lookup the class-prior q90 torque for ``(gear, rpm_bin)``.

        Returns None when the class key is unknown, the prior is empty
        (cold-start), or the requested cell isn't represented.

        Delegates directly to ``ClassPriorBuilder.read()`` each call —
        that layer already memoizes and invalidates on flush, so a second
        cache here would cause the cold-start bug described in FR-038:
        a class key seen before its first flush would cache an empty dict
        and never pick up the rows once the rebuild completes.

        O(n) walk where n ≤ ~1200 bins; at 30 Hz that is ~36k comparisons/s,
        well within v2 budget.
        """
        if class_key is None:
            return None
        try:
            bins = await self._class_prior.read(class_key)
        except Exception:
            _log.exception(
                "class_prior_read_failed class_key=%s gear=%d rpm_bin=%d",
                class_key,
                gear,
                rpm_bin,
            )
            return None
        for b in bins or []:
            if b.gear == gear and b.rpm_bin == rpm_bin:
                return float(b.q90_torque_nm)
        return None

    def _compute_display_active(
        self,
        *,
        stage: str,
        throttle: float,
        session_type: str,
    ) -> bool:
        """FR-020: compute whether the shift recommendation should be displayed."""
        if session_type == "drift":
            return False
        if throttle < self._cfg.shift_display_throttle_min:
            return False
        return stage != "fallback"

    def _compute_display_active_down(
        self,
        *,
        stage: str,
        throttle: float,
        brake: float,
        session_type: str,
        transmission_mode: TransmissionModeBlock,
        current_downshift_target: int | None,
    ) -> bool:
        """FR-049: compute whether the *downshift* marker should be displayed.

        True iff ALL of:
          - ``transmissionMode.mode != "auto"`` (manual / unknown both show).
          - ``session_type != "drift"``.
          - ``current_downshift_target`` is not None (resolver returned a
            viable pair for the current gear).
          - ``stage != "fallback"``.
          - ``brake >= shift_downshift_brake_display_min`` OR
            ``throttle < shift_downshift_throttle_display_max`` (the
            "in braking zone or off-throttle" condition).

        Independent of FR-020's upshift gate.
        """
        if transmission_mode.mode == "auto":
            return False
        if session_type == "drift":
            return False
        if stage == "fallback":
            return False
        if current_downshift_target is None:
            return False
        return not (
            brake < self._cfg.shift_downshift_brake_display_min
            and throttle >= self._cfg.shift_downshift_throttle_display_max
        )
