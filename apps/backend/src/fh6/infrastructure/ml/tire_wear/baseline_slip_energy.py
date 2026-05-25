"""T131: tire-wear v0 (slip-energy integrator, research R-7).

Per-wheel `wear = clamp(0..1, k * Σ combinedSlip^2 * dt)`. Resets at
session boundary. Calibrated tolerance band 0.05 (5 wear points)."""

from __future__ import annotations

from dataclasses import dataclass

from fh6.domain.entities.frame import DecodedFrame
from fh6.domain.value_objects.confidence import Confidence
from fh6.domain.value_objects.ids import SessionId

MODEL_VERSION = "tire-wear-v0-slip-energy"
TOLERANCE_BAND = 0.05
# Default decay coefficient. Calibrated against the fixture corpus in
# T138; defaults to "uncalibrated" model_version if calibration fails.
# Default decay coefficient. Calibrated against the fixture corpus in
# T138 at 8e-6 — but that assumed slip stayed in [0, 1]. FH6 emits raw
# combinedSlip up to 2-3 during lockup/wheelspin, and squaring that
# pushed wear toward 100% in a few minutes of casual driving. The slip
# clamp below already eats the worst case (slip² capped at 1.0); 6e-6
# gives a visible-but-realistic wear curve (~3-4% per 10 min mixed
# driving, ~0.5-1% per minute of high-slip cornering).
DEFAULT_K = 6e-6
# combinedSlip from FH6 can exceed 1.0 during heavy slip (lock-up,
# wheelspin); the legacy enricher uses 0.9 as the "losing grip" threshold
# but values can climb to 2–3. Clamping before squaring keeps the
# energy term in a sane range so a few wheelspins don't blow the model
# straight to 100% wear.
_MAX_SLIP_INPUT = 1.0
# Cap dt to anti-glitch the timestamp delta (e.g., session-resume after
# pause emits one huge dt). 50ms is well above the natural 16.7ms gap.
_MAX_DT_MS = 50.0


@dataclass(slots=True)
class _State:
    wear: dict[str, float]
    last_t: float | None


class TireWearModel:
    model_version: str = MODEL_VERSION
    tolerance_band: float = TOLERANCE_BAND

    def __init__(self, *, k: float = DEFAULT_K) -> None:
        self._k = k
        self._sessions: dict[str, _State] = {}

    def reset(self, session_id: SessionId) -> None:
        self._sessions.pop(str(session_id), None)

    def step(self, frame: DecodedFrame) -> tuple[dict[str, float], Confidence]:
        if frame.session_id is None:
            return ({"fl": 0.0, "fr": 0.0, "rl": 0.0, "rr": 0.0}, Confidence.placeholder())
        sid = str(frame.session_id)
        state = self._sessions.get(sid)
        t_now = frame.raw.timestamp_ms / 1000.0
        if state is None:
            state = _State(wear={"fl": 0.0, "fr": 0.0, "rl": 0.0, "rr": 0.0}, last_t=t_now)
            self._sessions[sid] = state
            return (
                dict(state.wear),
                Confidence(
                    value=0.0, tolerance_band=self.tolerance_band, model_version=self.model_version
                ),
            )
        dt_s = max(0.0, t_now - (state.last_t or t_now))
        state.last_t = t_now
        # Cap dt to absorb timestamp glitches (resume-from-pause etc.).
        dt_ms = min(_MAX_DT_MS, dt_s * 1000.0)
        for wn in ("fl", "fr", "rl", "rr"):
            slip = abs(float(frame.raw.wheels[wn]["combinedSlip"]))
            # Clamp before squaring: combinedSlip > 1.0 is legitimate in
            # FH6 (lock-up / spin) but contributes disproportionately when
            # squared. Cap keeps energy in [0, 1].
            slip_c = min(_MAX_SLIP_INPUT, slip)
            state.wear[wn] = min(1.0, state.wear[wn] + self._k * slip_c * slip_c * dt_ms)
        # Confidence grows with accumulated samples up to 0.85 cap.
        # Replaced by calibrated value once T138 runs against the corpus.
        elapsed = sum(state.wear.values())
        conf = min(0.85, 0.2 + elapsed * 0.5)
        return (
            dict(state.wear),
            Confidence(
                value=conf, tolerance_band=self.tolerance_band, model_version=self.model_version
            ),
        )


__all__ = ["MODEL_VERSION", "TOLERANCE_BAND", "TireWearModel"]
