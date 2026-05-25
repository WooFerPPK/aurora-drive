"""Modeled-tier emitter (T056 placeholder + T144 real model).

Two modes:
- placeholder mode (`apply_placeholder`) emits `modeled.tireWear = {0,0,0,0}` with
  `tireWearConfidence = 0` and `modeledByVersion = "placeholder"`. Used in
  legacy unit tests + as a degraded fallback.
- real mode (`apply_real_model`) drives the `TireWearModel` v0
  slip-energy integrator (research R-7) and writes calibrated wear
  values with the model's declared tolerance band and version.

Constitution Principle VI: modeled fields ALWAYS carry a confidence +
model_version, even when the implementation is a stub.
"""

from __future__ import annotations

from fh6.domain.entities.frame import DecodedFrame, FrameModeled
from fh6.domain.value_objects.confidence import Confidence

PLACEHOLDER_VERSION = "placeholder"
PACKET_VERSION = "packet"


def apply_placeholder(frame: DecodedFrame) -> DecodedFrame:
    # If the inbound packet already carried real tire-wear values
    # (Motorsport-style trailing block, see decoder + FrameRaw), prefer
    # them over the zero placeholder. Confidence=1.0 because the values
    # came straight from the game.
    if frame.raw.tire_wear_source == "packet" and frame.raw.tire_wear is not None:
        frame.modeled = FrameModeled(
            tire_wear=dict(frame.raw.tire_wear),
            tire_wear_confidence=Confidence(
                value=1.0,
                tolerance_band=0.0,
                model_version=PACKET_VERSION,
            ),
        )
        return frame
    frame.modeled = FrameModeled(
        tire_wear={"fl": 0.0, "fr": 0.0, "rl": 0.0, "rr": 0.0},
        tire_wear_confidence=Confidence(
            value=0.0,
            tolerance_band=0.0,
            model_version=PLACEHOLDER_VERSION,
        ),
    )
    return frame


def apply_real_model(frame: DecodedFrame, *, tire_wear_model) -> DecodedFrame:  # type: ignore[no-untyped-def]
    """T144: invoke the slip-energy TireWearModel. Real model output
    replaces the placeholder zero wear emitted by `apply_placeholder`.

    `tire_wear_model` is duck-typed: must expose `.step(frame) ->
    (dict, Confidence)`."""
    wear, conf = tire_wear_model.step(frame)
    frame.modeled = FrameModeled(tire_wear=wear, tire_wear_confidence=conf)
    return frame
